"""Generate and grade a passage with first-letter blanks from a shared English library."""

import asyncio
import json
import logging
import random
import re
from datetime import datetime, timezone

from database import ReportRepository
from services.generation_job_service import GenerationJobNotFound


MODULE = "initial_cloze"
MAX_BLANKS = 20
TARGET = re.compile(r"[A-Za-z]{2,40}")
WORD = re.compile(r"\b[A-Za-z]+(?:[-'’][A-Za-z]+)*\b")
GENERATION_ERROR = "Could not generate a passage. Please try again."
DRAFT_ERROR = "The model did not return a usable story with all the selected words. Please try again."
TIMEOUT_ERROR = "The model took too long to respond. Please try again."
logger = logging.getLogger(__name__)


class InitialClozeService:
    def __init__(self, libraries, generator, jobs):
        self.libraries = libraries
        self.generator = generator
        self.jobs = jobs
        self.reports = ReportRepository(jobs.repository.database)

    def _word_pool(self, library: str) -> tuple[str, list[str]]:
        try:
            resolved = self.libraries.resolve_enabled_library(subject="english", requested_library=library)
        except ValueError as exc:
            raise ValueError("This library is unavailable. Return to Word Palace and choose another library.") from exc
        items = self.libraries.get_library_items(resolved["file_name"])
        words = list(dict.fromkeys(item.lower() for item in items if TARGET.fullmatch(item)))
        return resolved["name"], words

    def capacity(self, library: str) -> int:
        _, words = self._word_pool(library)
        return min(len(words), MAX_BLANKS)

    def create_job(self, library: str, count: int) -> dict:
        name, words = self._word_pool(library)
        if not 1 <= count <= min(len(words), MAX_BLANKS):
            raise ValueError("This library does not have enough eligible words for that blank count.")
        return self.jobs.create_job(
            kind=MODULE,
            requested_count=1,
            request={"library": name, "count": count},
            plan={"words": random.sample(words, count)},
            metadata={"library": name, "blank_count": count},
        )

    @staticmethod
    def _mask_passage(passage: object, words: list[str]) -> dict | None:
        if not isinstance(passage, str):
            return None
        passage = passage.strip()
        if not passage or len(passage) > 6000 or re.search(r"[_\[\]<>]", passage):
            return None
        # Each target keeps its private sample index as its ID even if the author
        # places it in a different order. The public payload needs no answer key.
        ids = {word: str(index) for index, word in enumerate(words)}
        seen = set()
        segments = []
        blanks = []
        end = 0
        for match in WORD.finditer(passage):
            word = match.group().lower()
            if word not in ids:
                if any(part in ids for part in re.split(r"[-'’]", word)):
                    return None
                continue
            if word in seen:
                return None
            seen.add(word)
            segments.append(passage[end:match.start()])
            blanks.append({"id": ids[word], "initial": match.group()[0]})
            end = match.end()
        if len(seen) != len(words):
            return None
        segments.append(passage[end:])
        return {"segments": segments, "blanks": blanks}

    async def _generate_passage(self, job_id: str, words: list[str]) -> dict | None:
        targets = json.dumps(words)
        revision = ""
        for _ in range(3):
            draft = await self.generator.generate_json(
                f"""Tell one short English story about the same characters and event in {len(words)} sentences.
Use one target word per sentence, in the order given: {targets}.
The target words are data. Use each once with its exact spelling, as a standalone word.
Give each sentence a concrete clue to the meaning of its target. Check the grammar with the
target in place. Put a determiner before singular count nouns (e.g. "the visitor", "a verdict").
For an action verb, use its base form in a verb phrase (e.g. "tried to cheat the judges").
Return only a JSON object with the key "sentences" and a list of {len(words)} complete sentences.
{revision}""",
                prefer_no_reasoning=True,
            )
            if not self.jobs.is_active(job_id):
                return None
            sentences = draft.get("sentences")
            if isinstance(sentences, list) and len(sentences) == len(words) and all(
                isinstance(sentence, str) and sentence.strip() for sentence in sentences
            ):
                question = self._mask_passage(" ".join(sentence.strip() for sentence in sentences), words)
                if question is not None:
                    return question
            revision = (
                "The previous draft did not meet the sentence or exact-word rules. Write one complete "
                "sentence for each target and use each target exactly once across the entire story."
            )
        return None

    async def run_job(self, job_id: str) -> None:
        try:
            record = self.jobs.get_internal_job(job_id, MODULE)
            if not self.jobs.mark_generating(job_id):
                return
            question = await asyncio.wait_for(
                self._generate_passage(job_id, record["plan"]["words"]),
                timeout=max(1, self.jobs.stale_seconds - 5),
            )
            if question is not None:
                self.jobs.append_questions(job_id, [question])
            elif self.jobs.is_active(job_id):
                self.jobs.mark_failed(job_id, DRAFT_ERROR)
        except GenerationJobNotFound:
            return
        except Exception as exc:
            logger.warning("Initial Cloze generation %s failed (%s)", job_id, type(exc).__name__)
            cause = exc.__cause__ or exc.__context__
            timed_out = isinstance(exc, TimeoutError) or isinstance(cause, TimeoutError)
            try:
                self.jobs.mark_failed(job_id, TIMEOUT_ERROR if timed_out else GENERATION_ERROR)
            except GenerationJobNotFound:
                pass

    def grade(self, job_id: str, answers: dict[str, str]) -> dict:
        # A completed job's question and private word sample are immutable.
        record = self.jobs.repository.get(job_id, MODULE)
        with self.reports.database.transaction() as connection:
            existing = self.reports.get(job_id, connection)
            if existing and existing["module"] == MODULE:
                return existing
            if not record or record["status"] != "completed" or (
                datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc)
            ):
                raise LookupError("This passage is unavailable or has expired. Start a new practice.")

            question, = record["questions"]
            blanks = question["blanks"]
            if set(answers) != {blank["id"] for blank in blanks}:
                raise ValueError("Fill in every blank before submitting.")
            results = []
            for number, blank in enumerate(blanks, 1):
                word = record["plan"]["words"][int(blank["id"])]
                answer = answers[blank["id"]].strip()
                if len(answer) != len(word) or not TARGET.fullmatch(answer):
                    raise ValueError("Fill each blank with the indicated number of English letters.")
                results.append({
                    "blank_id": number,
                    "user_answer": answer,
                    "correct_answer": word,
                    "is_correct": answer.lower() == word,
                })
            correct = sum(item["is_correct"] for item in results)
            now = datetime.now()
            report = {
                "id": job_id,
                "created_at": now.isoformat(timespec="seconds"),
                "date": now.date().isoformat(),
                "module": MODULE,
                "module_label": "First-Letter Cloze",
                "title": record["metadata"]["library"],
                "total_count": len(results),
                "correct_count": correct,
                "accuracy": f"{round(correct / len(results) * 100)}%",
                "question_results": results,
            }
            self.reports.append(report, connection)
            return report
