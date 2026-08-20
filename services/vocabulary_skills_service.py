"""
Word Palace Vocabulary Skills 服务模块
提供 Vocabulary Skills 查询、技能树、题目生成、Detail 映射和诊断评估逻辑。
"""
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

from core.ai_generator import get_ai_generator
from models.schemas import (
    VocabularySkillsAnswerItem,
    VocabularySkillsEvaluateRequest,
    VocabularySkillsGenerateRequest,
)
from services.report_history_service import get_report_history_service
from services.skills_service import get_skills_service
from services.generation_job_service import GenerationJobNotFound, get_generation_job_service

logger = logging.getLogger(__name__)

MODULE = "word_palace"
SECTION = "vocabulary_skills"
REPORT_MODULE = "word_vocabulary_skills"
REPORT_LABEL = "Vocabulary Skills"

DIFFICULTY_RULES = {
    "easy": "Use common grade-level words and make distractors clearly wrong for one reason.",
    "medium": "Use closer distractors and require applying the vocabulary pattern in context.",
    "hard": "Use nuanced meanings, concise context, and plausible distractors that test common misconceptions.",
    "adaptive": "Use a balanced mix of easy, medium, and hard items across the selected Details."
}


class VocabularySkillsService:
    """Word Palace Vocabulary Skills 服务类"""

    def __init__(self):
        self.ai_generator = get_ai_generator()
        self.report_history_service = get_report_history_service()
        self.skills_service = get_skills_service()
        self.generation_job_service = get_generation_job_service()
        logger.info("VocabularySkillsService initialized")

    def get_skills(
        self,
        grade: Optional[str] = None,
        topic: Optional[str] = None,
        skill: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[Dict[str, Any]]:
        """按 Grade / Topic / Skill 查询明细，默认只返回启用 Detail。"""
        return self.skills_service.list_skills(
            module=MODULE,
            section=SECTION,
            grade=self._normalize_grade(grade) if grade else None,
            topic=topic,
            skill=skill,
            enabled_only=enabled_only
        )

    def get_skill_tree(self, enabled_only: bool = True) -> Dict[str, Any]:
        """生成 Grade -> Topic -> Skill -> Details 树。"""
        return self.skills_service.get_tree(module=MODULE, section=SECTION, enabled_only=enabled_only)

    def prepare_generation_job(self, request: VocabularySkillsGenerateRequest) -> Dict[str, Any]:
        """Freeze selected Details so background batches cover a stable practice plan."""
        selected_details = self._select_details_for_request(request)
        if not selected_details:
            raise ValueError("没有找到匹配的 Vocabulary Skills，请检查 Grade/Topic/Skill")
        return {"selected_details": selected_details}

    async def generate_prepared_batch(
        self,
        request: VocabularySkillsGenerateRequest,
        plan: Dict[str, Any],
        start: int,
        count: int,
    ) -> List[Dict[str, Any]]:
        all_details = list(plan.get("selected_details") or [])
        if not all_details:
            raise ValueError("Vocabulary Skills 生成计划没有可用 Detail")
        scheduled = [all_details[index % len(all_details)] for index in range(start, start + count)]
        selected_details = []
        seen = set()
        for detail in scheduled:
            key = str(detail.get("id") or detail.get("detail") or "")
            if key not in seen:
                seen.add(key)
                selected_details.append(detail)

        batch_request = request.model_copy(update={"question_count": count})
        prompt = self._build_generation_prompt(batch_request, selected_details)
        data = await self.ai_generator.generate_json(
            prompt,
            system_message="You are a vocabulary skills practice question generator. Output valid JSON only.",
            temperature=0.65,
        )
        questions = self._normalize_questions(
            data.get("questions", []),
            batch_request,
            selected_details,
            question_id_start=start + 1,
        )
        if len(questions) != count:
            raise ValueError(f"AI 本批应生成 {count} 题，实际有效题目为 {len(questions)} 题")
        return questions

    async def run_generation_job(self, job_id: str) -> None:
        try:
            record = self.generation_job_service.get_internal_job(job_id, "vocabulary_skills")
            if not self.generation_job_service.mark_generating(job_id):
                return
            request = VocabularySkillsGenerateRequest(**record["request"])
            total = int(record["requested_count"])
            start = 0
            while start < total and self.generation_job_service.is_active(job_id):
                batch_size = min(3 if start == 0 else 5, total - start)
                questions = await self.generate_prepared_batch(request, record["plan"], start, batch_size)
                if not self.generation_job_service.is_active(job_id):
                    return
                self.generation_job_service.append_questions(job_id, questions)
                start += batch_size
        except GenerationJobNotFound:
            logger.info("Vocabulary Skills generation job %s disappeared before completion", job_id)
        except Exception as exc:
            logger.error("Vocabulary Skills generation job %s failed: %s", job_id, exc)
            try:
                self.generation_job_service.mark_failed(job_id, str(exc))
            except GenerationJobNotFound:
                pass

    async def generate_practice(self, request: VocabularySkillsGenerateRequest) -> Dict[str, Any]:
        try:
            selected_details = self._select_details_for_request(request)
            if not selected_details:
                return {"error": "没有找到匹配的 Vocabulary Skills，请检查 Grade/Topic/Skill", "questions": []}

            prompt = self._build_generation_prompt(request, selected_details)
            data = await self.ai_generator.generate_json(
                prompt,
                system_message="You are a vocabulary skills practice question generator. Output valid JSON only.",
                temperature=0.65
            )
            questions = self._normalize_questions(data.get("questions", []), request, selected_details)
            if not questions:
                return {"error": "AI 未返回有效 Vocabulary Skills 题目", "questions": []}

            topic = request.topic or selected_details[0].get("topic", "Vocabulary")
            return {
                "test_title": data.get("test_title", "Vocabulary Skills Practice"),
                "grade_level": self._normalize_grade(request.grade_level),
                "topic": topic,
                "skill": request.skill,
                "difficulty": request.difficulty,
                "question_count": len(questions),
                "questions": questions
            }
        except Exception as e:
            logger.error(f"Error generating Vocabulary Skills practice: {str(e)}")
            return {"error": str(e), "questions": []}

    async def evaluate_practice(self, request: VocabularySkillsEvaluateRequest) -> Dict[str, Any]:
        results = self._grade_locally(request.questions, request.answers)
        metadata = self._build_report_metadata(request, results)
        report = self._build_report(results, metadata)

        self.report_history_service.add_report({
            "module": REPORT_MODULE,
            "module_label": REPORT_LABEL,
            "title": "Vocabulary Skills Practice",
            "grade_level": report["grade_level"],
            "topic": report["topic"],
            "skill": report["skill"],
            "skill_area": report["skill"],
            "difficulty": report["difficulty"],
            "question_count": report["question_count"],
            "score": report["score"],
            "accuracy": report["accuracy"],
            "total_count": report["total_count"],
            "correct_count": report["correct_count"],
            "summary": report["student_summary"],
            "skill_breakdown": report["skill_breakdown"],
            "detail_breakdown": report["detail_breakdown"],
            "weak_knowledge_points": report["weak_knowledge_points"],
            "recommended_next_practice": report["recommended_next_practice"],
            "question_results": results[:50],
            "details": {
                "grade_level": report["grade_level"],
                "topic": report["topic"],
                "skill": report["skill"],
                "difficulty": report["difficulty"],
                "question_count": report["question_count"],
                "detail_breakdown": report["detail_breakdown"],
                "question_results": results[:50]
            }
        })
        return report

    def _build_report_metadata(
        self,
        request: VocabularySkillsEvaluateRequest,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        first = results[0] if results else {}
        return {
            "grade_level": self._normalize_grade(request.grade_level or first.get("grade_level", "")),
            "topic": request.topic or first.get("topic", ""),
            "skill": request.skill or first.get("skill", ""),
            "difficulty": request.difficulty or first.get("difficulty", ""),
            "question_count": int(request.question_count or len(results) or 0)
        }

    def _select_details_for_request(self, request: VocabularySkillsGenerateRequest) -> List[Dict[str, Any]]:
        rows = self.get_skills(
            grade=request.grade_level,
            topic=request.topic,
            skill=request.skill,
            enabled_only=True
        )
        focus = str(request.detail_focus or "").strip().lower()
        if focus:
            focused = [
                row for row in rows
                if focus == str(row.get("detail", "")).strip().lower()
                or focus in str(row.get("detail", "")).strip().lower()
            ]
            if focused:
                return focused
        return rows

    def _normalize_grade(self, grade_level: Optional[str]) -> str:
        text = str(grade_level or "").strip()
        if not text:
            return ""
        if text.lower().startswith("grade"):
            return "Grade " + text.split()[-1]
        return f"Grade {text}"

    def _build_generation_prompt(
        self,
        request: VocabularySkillsGenerateRequest,
        selected_details: List[Dict[str, Any]]
    ) -> str:
        grade = self._normalize_grade(request.grade_level)
        topic = request.topic or selected_details[0].get("topic", "Vocabulary")
        details_text = "\n".join(
            f"- detail_id: {item.get('id')} | detail: {item.get('detail')}"
            for item in selected_details
        )
        labels = ["A", "B", "C", "D", "E"][:request.option_count]
        choices_schema = ",\n        ".join(f'"{label}": ""' for label in labels)

        return f"""
Generate original multiple-choice vocabulary skills practice questions.

Return valid JSON only.

Target settings:
- grade_level: {grade}
- topic: {topic}
- skill: {request.skill}
- detail_focus: {request.detail_focus or 'none'}
- difficulty: {request.difficulty}
- question_count: {request.question_count}
- option_count: {request.option_count}
- include_explanation: {str(request.include_explanation).lower()}

Cover multiple Details from the list when possible. The student should never choose a Detail.
If detail_focus is not "none", generate all questions for that focused Detail.

Available Details:
{details_text}

Difficulty rule:
{DIFFICULTY_RULES.get(request.difficulty, DIFFICULTY_RULES["medium"])}

Question requirements:
- Create original questions. Do not copy real IXL, MAP, or textbook questions.
- Each question must have exactly one correct answer.
- Use exactly {request.option_count} answer choices with labels {", ".join(labels)}.
- Keep wording age-appropriate for {grade}.
- Provide all needed context in question_stem or passage_or_sentence.
- Put the tested Detail in `detail`. You may use either the detail_id or the exact detail text.
- Explanations should be short and student-friendly.
- Do not reveal internal detail ids in explanations.

JSON schema:
{{
  "test_title": "Vocabulary Skills Practice",
  "questions": [
    {{
      "question_id": 1,
      "grade_level": "{grade}",
      "topic": "{topic}",
      "skill": "{request.skill}",
      "detail": "",
      "difficulty": "{request.difficulty}",
      "question_stem": "",
      "passage_or_sentence": "",
      "answer_choices": {{
        {choices_schema}
      }},
      "correct_answer": "A",
      "explanation": "",
      "tested_word": "",
      "common_error_tested": ""
    }}
  ]
}}

Rules:
1. Do not include markdown.
2. Do not include commentary outside JSON.
3. Generate exactly {request.question_count} questions.
"""

    def _normalize_questions(
        self,
        raw_questions: Any,
        request: VocabularySkillsGenerateRequest,
        selected_details: List[Dict[str, Any]],
        question_id_start: int = 1,
    ) -> List[Dict[str, Any]]:
        if not isinstance(raw_questions, list):
            return []

        normalized: List[Dict[str, Any]] = []
        valid_labels = ["A", "B", "C", "D", "E"][:request.option_count]
        grade = self._normalize_grade(request.grade_level)
        topic = request.topic or (selected_details[0].get("topic") if selected_details else "Vocabulary")

        for idx, raw in enumerate(raw_questions[:request.question_count], start=1):
            if not isinstance(raw, dict):
                continue

            choices = raw.get("answer_choices") or raw.get("choices") or raw.get("options") or {}
            if isinstance(choices, list):
                choices = {label: str(value) for label, value in zip(valid_labels, choices)}
            if not isinstance(choices, dict):
                continue

            cleaned_choices = {
                str(label).upper()[:1]: str(value).strip()
                for label, value in choices.items()
                if str(label).upper()[:1] in valid_labels and str(value).strip()
            }
            if len(cleaned_choices) < request.option_count:
                continue

            answer = self._normalize_answer(raw.get("correct_answer", raw.get("answer", "")), cleaned_choices)
            if not answer:
                continue

            readable_detail = self._resolve_detail_label(
                raw.get("detail_id") or raw.get("detail") or raw.get("subskill") or "",
                selected_details
            )
            if not readable_detail and selected_details:
                readable_detail = selected_details[(idx - 1) % len(selected_details)].get("detail", "")

            normalized.append({
                "question_id": question_id_start + idx - 1,
                "grade_level": raw.get("grade_level") or grade,
                "topic": raw.get("topic") or topic,
                "skill": raw.get("skill") or request.skill,
                "detail": readable_detail,
                "difficulty": raw.get("difficulty") or request.difficulty,
                "question_stem": str(raw.get("question_stem") or raw.get("sentence") or "Choose the best answer.").strip(),
                "passage_or_sentence": str(raw.get("passage_or_sentence") or raw.get("passage") or "").strip(),
                "answer_choices": {label: cleaned_choices[label] for label in valid_labels if label in cleaned_choices},
                "correct_answer": answer,
                "explanation": str(raw.get("explanation") or raw.get("analysis") or "").strip(),
                "tested_word": str(raw.get("tested_word") or raw.get("word") or "").strip(),
                "common_error_tested": str(raw.get("common_error_tested") or "").strip()
            })

        return normalized

    def _resolve_detail_label(self, value: Any, selected_details: List[Dict[str, Any]]) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        lower_text = text.lower()
        for item in selected_details:
            detail_id = str(item.get("id") or "").strip()
            detail_text = str(item.get("detail") or "").strip()
            if text == detail_text:
                return detail_text
            if detail_id and text == detail_id:
                return detail_text
            if detail_id and detail_id in text:
                return detail_text
            if detail_text and lower_text == detail_text.lower():
                return detail_text
        return text

    def _normalize_answer(self, answer: Any, choices: Dict[str, str]) -> Union[str, List[str], None]:
        if isinstance(answer, list):
            labels = [str(item).upper()[:1] for item in answer]
            labels = [label for label in labels if label in choices]
            return sorted(set(labels)) if labels else None

        label = str(answer).strip().upper()[:1]
        if label in choices:
            return label

        answer_text = str(answer).strip().lower()
        for choice_label, choice_text in choices.items():
            if choice_text.strip().lower() == answer_text:
                return choice_label
        return None

    def _grade_locally(
        self,
        questions: List[Any],
        answers: List[VocabularySkillsAnswerItem]
    ) -> List[Dict[str, Any]]:
        answer_map = {item.question_id: item.student_answer for item in answers}
        results: List[Dict[str, Any]] = []

        for q in questions:
            student_answer = answer_map.get(q.question_id, "")
            is_correct = self._answers_equal(student_answer, q.correct_answer)
            readable_detail = self._resolve_detail_from_any(q.detail)
            results.append({
                "question_id": q.question_id,
                "grade_level": q.grade_level,
                "topic": q.topic,
                "skill": q.skill,
                "detail": readable_detail,
                "difficulty": q.difficulty,
                "question_stem": q.question_stem,
                "student_answer": student_answer,
                "correct_answer": q.correct_answer,
                "is_correct": is_correct,
                "explanation": q.explanation or "",
                "tested_word": q.tested_word or "",
                "common_error_tested": q.common_error_tested or ""
            })
        return results

    def _resolve_detail_from_any(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if not text.startswith("word_palace_vocabulary_skills_"):
            return text
        return self._resolve_detail_label(text, self.get_skills(enabled_only=False))

    def _answers_equal(self, student_answer: Any, correct_answer: Any) -> bool:
        def normalize(value: Any) -> List[str]:
            raw = value if isinstance(value, list) else [value]
            return sorted(str(item).strip().upper()[:1] for item in raw if str(item).strip())

        return normalize(student_answer) == normalize(correct_answer)

    def _build_report(self, results: List[Dict[str, Any]], metadata: Dict[str, Any]) -> Dict[str, Any]:
        total = len(results)
        correct = sum(1 for item in results if item["is_correct"])
        score = round((correct / total) * 100, 2) if total else 0
        accuracy = f"{round(score)}%"

        breakdown = self._build_skill_breakdown(results)
        detail_breakdown = self._build_detail_breakdown(results)
        weak_points = self._build_weak_knowledge_points(detail_breakdown)
        recommendations = self._build_recommendations(weak_points, results, score)

        return {
            "module": REPORT_MODULE,
            "module_label": REPORT_LABEL,
            **metadata,
            "score": score,
            "accuracy": accuracy,
            "total": total,
            "total_count": total,
            "correct_count": correct,
            "overall": {
                "total_questions": total,
                "correct": correct,
                "accuracy": accuracy
            },
            "detail_breakdown": detail_breakdown,
            "question_results": results,
            "weak_knowledge_points": weak_points,
            "recommended_next_practice": recommendations,
            "skill_breakdown": breakdown,
            "student_summary": self._build_student_summary(score, weak_points),
            "parent_teacher_summary": "This report groups Vocabulary Skills results by real Detail text and recommends targeted next practice."
        }

    def _build_skill_breakdown(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in results:
            grouped[item.get("skill") or "Vocabulary"].append(item)

        rows = []
        for skill, items in grouped.items():
            total = len(items)
            correct = sum(1 for item in items if item["is_correct"])
            accuracy = round(correct / total * 100) if total else 0
            rows.append({
                "skill": skill,
                "total": total,
                "correct": correct,
                "accuracy": f"{accuracy}%",
                "diagnosis": self._diagnose_accuracy(skill, accuracy)
            })
        return rows

    def _build_detail_breakdown(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in results:
            detail = self._resolve_detail_from_any(item.get("detail") or item.get("skill") or "Vocabulary")
            if detail not in grouped:
                grouped[detail] = {
                    "detail": detail,
                    "grade_level": item.get("grade_level", ""),
                    "topic": item.get("topic", ""),
                    "skill": item.get("skill", ""),
                    "total": 0,
                    "correct": 0,
                    "wrong_count": 0,
                    "missed_count": 0,
                    "question_ids": [],
                    "missed_question_ids": [],
                    "accuracy": "0%"
                }
            grouped[detail]["total"] += 1
            grouped[detail]["question_ids"].append(item.get("question_id"))
            if item.get("is_correct"):
                grouped[detail]["correct"] += 1
            else:
                grouped[detail]["wrong_count"] += 1
                grouped[detail]["missed_count"] += 1
                grouped[detail]["missed_question_ids"].append(item.get("question_id"))

        rows = []
        for row in grouped.values():
            total = row["total"]
            correct = row["correct"]
            accuracy_num = round(correct / total * 100) if total else 0
            row["accuracy"] = f"{accuracy_num}%"
            row["accuracy_value"] = accuracy_num
            rows.append(row)
        return sorted(rows, key=lambda item: (item.get("skill", ""), item.get("detail", "")))

    def _build_weak_knowledge_points(self, detail_breakdown: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        candidates = [row for row in detail_breakdown if int(row.get("wrong_count") or 0) > 0]
        candidates.sort(key=lambda item: (-int(item.get("wrong_count") or 0), int(item.get("accuracy_value") or 0), item.get("detail", "")))

        weak_points = []
        for row in candidates[:3]:
            missed_count = int(row.get("wrong_count") or row.get("missed_count") or 0)
            point = {
                "knowledge_point": row.get("detail", ""),
                "detail": row.get("detail", ""),
                "grade_level": row.get("grade_level", ""),
                "topic": row.get("topic", ""),
                "skill": row.get("skill", ""),
                "total": int(row.get("total") or 0),
                "correct": int(row.get("correct") or 0),
                "wrong_count": missed_count,
                "missed_count": missed_count,
                "accuracy": row.get("accuracy", "0%"),
                "question_ids": row.get("missed_question_ids", []),
                "severity": "high" if missed_count >= 2 or int(row.get("accuracy_value") or 0) < 50 else "medium",
                "message": f"Practice {row.get('detail', '')} because its accuracy was {row.get('accuracy', '0%')}."
            }
            weak_points.append(point)
        return weak_points

    def _build_recommendations(
        self,
        weak_points: List[Dict[str, Any]],
        results: List[Dict[str, Any]],
        score: float
    ) -> List[Dict[str, Any]]:
        difficulty = "easy" if score < 60 else "medium"
        recommendations = [
            {
                "grade_level": point.get("grade_level", ""),
                "topic": point.get("topic", "Vocabulary"),
                "skill": point.get("skill", ""),
                "detail": point.get("detail", point["knowledge_point"]),
                "question_count": 10,
                "difficulty": difficulty,
                "advice": f"Review examples for {point.get('detail', point['knowledge_point'])}, then try a short focused set.",
                "reason": f"Focus on {point.get('detail', point['knowledge_point'])} after missed questions."
            }
            for point in weak_points[:3]
        ]
        if recommendations:
            return recommendations

        if not results:
            return []
        first = results[0]
        return [{
            "grade_level": first.get("grade_level", ""),
            "topic": first.get("topic", "Vocabulary"),
            "skill": first.get("skill", ""),
            "detail": "Mixed review",
            "question_count": 10,
            "difficulty": "medium",
            "advice": "Move to a mixed review set to keep this skill fresh.",
            "reason": "Accuracy is strong. Continue with mixed review or a harder set."
        }]

    def _diagnose_accuracy(self, skill: str, accuracy: int) -> str:
        if accuracy >= 85:
            return f"Strong performance in {skill}. Try harder or mixed practice next."
        if accuracy >= 65:
            return f"Developing performance in {skill}. A short focused review should help."
        return f"Needs focused practice in {skill}. Review explanations and retry easier questions."

    def _build_student_summary(self, score: float, weak_points: List[Dict[str, Any]]) -> str:
        if not weak_points and score >= 85:
            return "Great work. Your Vocabulary Skills accuracy is strong, so a harder mixed review is a good next step."
        if weak_points:
            details = ", ".join(point["detail"] for point in weak_points[:2])
            return f"Good effort. Review the missed questions and practice these Details next: {details}."
        return "Good effort. Review the explanations and try another short Vocabulary Skills set."


_vocabulary_skills_service: Optional[VocabularySkillsService] = None


def get_vocabulary_skills_service() -> VocabularySkillsService:
    global _vocabulary_skills_service
    if _vocabulary_skills_service is None:
        _vocabulary_skills_service = VocabularySkillsService()
    return _vocabulary_skills_service
