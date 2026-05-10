"""
MAP Language Arts 服务模块
提供 Language Arts 技能树、题目生成和诊断评估逻辑。
"""
import logging
from collections import defaultdict
from typing import Any, Dict, List, Union

from core.ai_generator import get_ai_generator
from services.report_history_service import get_report_history_service
from models.schemas import (
    MapLanguageArtsAnswerItem,
    MapLanguageArtsEvaluateRequest,
    MapLanguageArtsGenerateRequest,
)

logger = logging.getLogger(__name__)


LANGUAGE_ARTS_SKILLS: List[Dict[str, Any]] = [
    {
        "key": "grammar_usage",
        "title": "Grammar & Usage",
        "cn": "语法与用法",
        "summary": "Verb tense, subject-verb agreement, pronoun case, possessives, comparatives, conjunctions, and clauses.",
        "question_types": [
            "Choose the correct word.",
            "Which sentence is written correctly?",
            "Which sentence has the same meaning?"
        ],
        "subskills": ["verb tense", "subject-verb agreement", "pronoun case", "possessives", "comparatives", "clauses"]
    },
    {
        "key": "pronoun_reference",
        "title": "Pronoun Reference",
        "cn": "代词指代",
        "summary": "Vague pronouns and clear noun replacement for it, they, this, that, he, she, and them.",
        "question_types": ["Which revision corrects the vague pronoun?", "Which change makes the sentence clearer?"],
        "subskills": ["vague pronouns", "clear noun replacement", "pronoun agreement"]
    },
    {
        "key": "punctuation",
        "title": "Punctuation",
        "cn": "标点",
        "summary": "Commas, quotation marks, ending punctuation, ellipses, addresses, dialogue, and direct speech.",
        "question_types": ["Choose the correctly punctuated sentence.", "Where does the comma belong?"],
        "subskills": ["commas", "dialogue punctuation", "quotation marks", "ellipsis", "addresses"]
    },
    {
        "key": "capitalization",
        "title": "Capitalization",
        "cn": "大小写",
        "summary": "Letter greetings, names, titles, places, sentence beginnings, and closings.",
        "question_types": ["Choose the correctly capitalized note.", "Which sentence uses capitalization correctly?"],
        "subskills": ["proper nouns", "sentence beginnings", "letters", "titles", "places"]
    },
    {
        "key": "sentence_combining",
        "title": "Sentence Combining",
        "cn": "句子合并",
        "summary": "Use because, although, if, when, even though, and other connectors while keeping the original meaning.",
        "question_types": ["Which sentence has the same meaning as the sentences above?", "Which revision best combines the sentences?"],
        "subskills": ["cause and effect", "contrast", "condition", "time order", "connectors"]
    },
    {
        "key": "sentence_revision",
        "title": "Sentence Revision",
        "cn": "句子修改",
        "summary": "Complete sentences, sentence errors, repetition, wordiness, clearer wording, and sentence order.",
        "question_types": ["Which sentence should be used because it is complete and correct?", "Which revision improves the sentence?"],
        "subskills": ["complete sentences", "fragments", "run-ons", "wordiness", "clarity"]
    },
    {
        "key": "paragraph_organization",
        "title": "Paragraph Organization",
        "cn": "段落组织",
        "summary": "Topic sentences, beginnings, conclusions, supporting details, and paragraph order.",
        "question_types": ["Which sentence best begins the paragraph?", "Which sentence best supports the main idea?"],
        "subskills": ["topic sentence", "supporting detail", "conclusion", "paragraph order", "main idea"]
    },
    {
        "key": "research_source_integration",
        "title": "Research & Source Integration",
        "cn": "信息整合",
        "summary": "Combine notes from two sources, judge evidence, and identify details that support a claim.",
        "question_types": ["Which two notes accurately combine information from both sources?", "Which detail best supports the claim?"],
        "subskills": ["source comparison", "evidence", "claims", "note synthesis", "supporting details"]
    },
    {
        "key": "mixed_review",
        "title": "Mixed Review",
        "cn": "综合复习",
        "summary": "A mixed set across multiple Language Arts skills for review after diagnosis.",
        "question_types": ["Mixed MAP-style Language Arts questions."],
        "subskills": ["mixed review"]
    }
]

SKILL_MAP = {skill["key"]: skill for skill in LANGUAGE_ARTS_SKILLS}
DIFFICULTY_RULES = {
    "easy": "Use short sentences, test one skill at a time, and make distractor errors clear.",
    "medium": "Use slightly longer sentences, closer distractors, and require understanding of meaning.",
    "hard": "Use short paragraphs or two sources when appropriate; distractors may be grammatical but semantically wrong.",
    "adaptive": "Start at medium difficulty and include a range of easy, medium, and hard questions."
}


class MapLanguageArtsService:
    """MAP Language Arts 服务类"""

    def __init__(self):
        self.ai_generator = get_ai_generator()
        self.report_history_service = get_report_history_service()
        logger.info("MapLanguageArtsService initialized")

    def get_skills(self) -> List[Dict[str, Any]]:
        return LANGUAGE_ARTS_SKILLS

    async def generate_practice(self, request: MapLanguageArtsGenerateRequest) -> Dict[str, Any]:
        try:
            prompt = self._build_generation_prompt(request)
            data = await self.ai_generator.generate_json(
                prompt,
                system_message="You are a MAP Language Arts practice question generator. Output valid JSON only.",
                temperature=0.65
            )
            questions = self._normalize_questions(data.get("questions", []), request)
            if not questions:
                return {"error": "AI 未返回有效 Language Arts 题目", "questions": []}

            return {
                "test_title": data.get("test_title", "MAP Language Arts Practice"),
                "grade_level": str(request.grade_level),
                "skill_area": request.skill_area,
                "difficulty": request.difficulty,
                "question_count": len(questions),
                "questions": questions
            }
        except Exception as e:
            logger.error(f"Error generating MAP Language Arts practice: {str(e)}")
            return {"error": str(e), "questions": []}

    async def evaluate_practice(self, request: MapLanguageArtsEvaluateRequest) -> Dict[str, Any]:
        results = self._grade_locally(request.questions, request.answers)
        base_report = self._build_base_report(results)

        try:
            prompt = self._build_evaluation_prompt(results, base_report)
            ai_report = await self.ai_generator.generate_json(
                prompt,
                system_message="You are a MAP Language Arts learning evaluator. Output valid JSON only.",
                temperature=0.35
            )
            report = self._merge_report(base_report, ai_report)
        except Exception as e:
            logger.warning(f"AI evaluation failed, using local report: {str(e)}")
            report = base_report

        report["results"] = results
        overall = report.get("overall", {})
        self.report_history_service.add_report({
            "module": "map_language_arts",
            "module_label": "MAP Language Arts",
            "title": "MAP Language Arts Practice",
            "skill_area": results[0].get("skill_area") if results else "mixed_review",
            "score": self._accuracy_to_number(overall.get("accuracy")),
            "total_count": int(overall.get("total_questions") or len(results)),
            "correct_count": int(overall.get("correct") or 0),
            "summary": report.get("student_summary", ""),
            "skill_breakdown": report.get("skill_breakdown", []),
            "weak_knowledge_points": report.get("weak_knowledge_points", []),
            "recommended_next_practice": report.get("recommended_next_practice", []),
            "details": {
                "results": results[:50]
            }
        })
        return report

    def _accuracy_to_number(self, value: Any) -> float:
        try:
            return float(str(value).replace("%", ""))
        except (TypeError, ValueError):
            return 0.0

    def _build_generation_prompt(self, request: MapLanguageArtsGenerateRequest) -> str:
        skill = SKILL_MAP.get(request.skill_area, SKILL_MAP["grammar_usage"])
        supported = "\n".join(f"- {item['key']}" for item in LANGUAGE_ARTS_SKILLS)
        return f"""
Generate MAP-style Language Arts practice questions.

Return valid JSON only.

Target settings:
- skill_area: {request.skill_area}
- skill_title: {skill['title']}
- subskill_focus: {request.subskill_focus or 'none'}
- grade_level: {request.grade_level}
- difficulty: {request.difficulty}
- question_count: {request.question_count}
- option_count: {request.option_count}
- include_explanation: {str(request.include_explanation).lower()}

Supported skill_area values:
{supported}

Skill focus:
{skill['summary']}

Specific knowledge point focus:
{request.subskill_focus or 'Use the most important subskills for this skill area.'}

Typical question types:
{'; '.join(skill['question_types'])}

Difficulty rule:
{DIFFICULTY_RULES.get(request.difficulty, DIFFICULTY_RULES['medium'])}

Question requirements:
- Create original practice questions. Do not copy real MAP/NWEA questions.
- Each question must have exactly one correct answer unless the question stem explicitly says "Choose two".
- Distractors must be plausible and based on common student mistakes.
- Avoid trick questions where more than one answer could be defended.
- Use age-appropriate vocabulary for grade {request.grade_level}.
- Do not require outside knowledge.
- Provide all needed text in passage_or_sentence.
- Keep passages short unless the selected skill requires two short sources.
- The correct answer must be unambiguous.
- Explanations should be short and student-friendly.
- Put the exact tested knowledge point in `subskill`, such as `vague pronouns`, `subject-verb agreement`, or `capitalization in letters`.
- Put the common mistake in `common_error_tested`, such as `unclear it reference` or `lowercase proper noun`.

JSON schema:
{{
  "test_title": "MAP Language Arts Practice",
  "grade_level": "{request.grade_level}",
  "skill_area": "{request.skill_area}",
  "question_count": {request.question_count},
  "questions": [
    {{
      "question_id": 1,
      "skill_area": "{request.skill_area}",
      "subskill": "",
      "difficulty": "{request.difficulty}",
      "question_stem": "",
      "passage_or_sentence": "",
      "answer_choices": {{
        "A": "",
        "B": "",
        "C": "",
        "D": ""
      }},
      "correct_answer": "A",
      "explanation": "",
      "common_error_tested": ""
    }}
  ]
}}

Rules:
1. Do not include markdown.
2. Do not include commentary outside JSON.
3. Use answer choice labels as correct_answer, such as "A" or ["A", "C"] only for explicit Choose two questions.
4. Generate exactly {request.question_count} questions.
"""

    def _normalize_questions(self, raw_questions: Any, request: MapLanguageArtsGenerateRequest) -> List[Dict[str, Any]]:
        if not isinstance(raw_questions, list):
            return []

        normalized: List[Dict[str, Any]] = []
        valid_labels = ["A", "B", "C", "D", "E"][:request.option_count]

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
            if len(cleaned_choices) < 4:
                continue

            answer = raw.get("correct_answer", raw.get("answer", ""))
            answer = self._normalize_answer(answer, cleaned_choices)
            if not answer:
                continue

            normalized.append({
                "question_id": int(raw.get("question_id") or idx),
                "skill_area": raw.get("skill_area") or request.skill_area,
                "subskill": raw.get("subskill") or request.subskill_focus or SKILL_MAP.get(request.skill_area, {}).get("subskills", [""])[0],
                "difficulty": raw.get("difficulty") or request.difficulty,
                "question_stem": str(raw.get("question_stem") or raw.get("sentence") or "Choose the best answer.").strip(),
                "passage_or_sentence": str(raw.get("passage_or_sentence") or raw.get("passage") or raw.get("sentence") or "").strip(),
                "answer_choices": {label: cleaned_choices[label] for label in valid_labels if label in cleaned_choices},
                "correct_answer": answer,
                "explanation": str(raw.get("explanation") or raw.get("analysis") or "").strip(),
                "common_error_tested": str(raw.get("common_error_tested") or "").strip()
            })

        return normalized

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
        answers: List[MapLanguageArtsAnswerItem]
    ) -> List[Dict[str, Any]]:
        answer_map = {item.question_id: item.student_answer for item in answers}
        results: List[Dict[str, Any]] = []

        for q in questions:
            student_answer = answer_map.get(q.question_id, "")
            is_correct = self._answers_equal(student_answer, q.correct_answer)
            results.append({
                "question_id": q.question_id,
                "skill_area": q.skill_area,
                "subskill": q.subskill,
                "difficulty": q.difficulty,
                "question_stem": q.question_stem,
                "student_answer": student_answer,
                "correct_answer": q.correct_answer,
                "is_correct": is_correct,
                "explanation": q.explanation or "",
                "common_error_tested": q.common_error_tested or ""
            })
        return results

    def _answers_equal(self, student_answer: Any, correct_answer: Any) -> bool:
        def normalize(value: Any) -> List[str]:
            if isinstance(value, list):
                raw = value
            else:
                raw = [value]
            return sorted(str(item).strip().upper()[:1] for item in raw if str(item).strip())

        return normalize(student_answer) == normalize(correct_answer)

    def _build_base_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(results)
        correct = sum(1 for item in results if item["is_correct"])
        accuracy = round((correct / total) * 100) if total else 0

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in results:
            grouped[item["skill_area"]].append(item)

        breakdown = []
        for skill_area, items in grouped.items():
            skill_total = len(items)
            skill_correct = sum(1 for item in items if item["is_correct"])
            skill_accuracy = round((skill_correct / skill_total) * 100) if skill_total else 0
            breakdown.append({
                "skill_area": skill_area,
                "total": skill_total,
                "correct": skill_correct,
                "accuracy": f"{skill_accuracy}%",
                "diagnosis": self._diagnose_skill(skill_area, skill_accuracy)
            })

        sorted_breakdown = sorted(breakdown, key=lambda item: int(str(item["accuracy"]).rstrip("%")))
        weakest = [item["skill_area"] for item in sorted_breakdown[:2] if item["total"]]
        strongest = [item["skill_area"] for item in sorted_breakdown[-2:] if item["total"]]
        error_patterns = [item["common_error_tested"] for item in results if not item["is_correct"] and item.get("common_error_tested")]
        weak_points = self._build_weak_knowledge_points(results)

        recommended = [
            {
                "skill_area": point["skill_area"],
                "subskill_focus": point["knowledge_point"],
                "question_count": 10,
                "difficulty": "easy" if accuracy < 60 else "medium",
                "reason": f"Practice {point['knowledge_point']} because it appeared in missed questions."
            }
            for point in weak_points[:3]
        ]
        if not recommended:
            recommended = [
                {
                    "skill_area": skill,
                    "subskill_focus": None,
                    "question_count": 10,
                    "difficulty": "easy" if accuracy < 60 else "medium",
                    "reason": "Focus here because recent answers show repeated mistakes in this skill."
                }
                for skill in weakest
            ]

        return {
            "overall": {
                "total_questions": total,
                "correct": correct,
                "accuracy": f"{accuracy}%"
            },
            "skill_breakdown": breakdown,
            "strongest_skills": strongest,
            "weakest_skills": weakest,
            "error_patterns": error_patterns[:6],
            "weak_knowledge_points": weak_points,
            "recommended_next_practice": recommended,
            "student_summary": "Great effort. Review the missed questions and practice the weakest skill next.",
            "parent_teacher_summary": "The report highlights accuracy by Language Arts skill and recommends focused next practice."
        }

    def _diagnose_skill(self, skill_area: str, accuracy: int) -> str:
        skill_title = SKILL_MAP.get(skill_area, {}).get("title", skill_area)
        if accuracy >= 85:
            return f"Strong performance in {skill_title}. Continue with harder or mixed practice."
        if accuracy >= 65:
            return f"Developing performance in {skill_title}. A short focused review should help."
        return f"Needs focused practice in {skill_title}. Review explanations and try another targeted set."

    def _build_weak_knowledge_points(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[tuple[str, str], Dict[str, Any]] = {}
        for item in results:
            if item.get("is_correct"):
                continue
            skill_area = item.get("skill_area") or "mixed_review"
            knowledge_point = item.get("common_error_tested") or item.get("subskill") or skill_area
            key = (skill_area, knowledge_point)
            if key not in grouped:
                grouped[key] = {
                    "skill_area": skill_area,
                    "knowledge_point": knowledge_point,
                    "subskill": item.get("subskill") or knowledge_point,
                    "missed_count": 0,
                    "question_ids": [],
                    "severity": "medium"
                }
            grouped[key]["missed_count"] += 1
            grouped[key]["question_ids"].append(item.get("question_id"))

        weak_points = sorted(grouped.values(), key=lambda x: x["missed_count"], reverse=True)
        for point in weak_points:
            point["severity"] = "high" if point["missed_count"] >= 2 else "medium"
            point["message"] = f"{point['knowledge_point']} needs focused practice."
        return weak_points[:5]

    def _build_evaluation_prompt(self, results: List[Dict[str, Any]], base_report: Dict[str, Any]) -> str:
        compact_results = [
            {
                "question_id": item["question_id"],
                "skill_area": item["skill_area"],
                "subskill": item["subskill"],
                "is_correct": item["is_correct"],
                "student_answer": item["student_answer"],
                "correct_answer": item["correct_answer"],
                "common_error_tested": item["common_error_tested"]
            }
            for item in results
        ]
        return f"""
You are a MAP Language Arts learning evaluator.

Analyze the student's answers by skill area and return valid JSON only.

Base scoring data:
{base_report}

Question results:
{compact_results}

Output JSON schema:
{{
  "overall": {{"total_questions": 0, "correct": 0, "accuracy": "0%"}},
  "skill_breakdown": [
    {{"skill_area": "", "total": 0, "correct": 0, "accuracy": "0%", "diagnosis": ""}}
  ],
  "strongest_skills": [],
  "weakest_skills": [],
  "error_patterns": [],
  "weak_knowledge_points": [
    {{"skill_area": "", "knowledge_point": "", "subskill": "", "missed_count": 1, "severity": "medium", "message": ""}}
  ],
  "recommended_next_practice": [
    {{"skill_area": "", "subskill_focus": "", "question_count": 10, "difficulty": "medium", "reason": ""}}
  ],
  "student_summary": "",
  "parent_teacher_summary": ""
}}

Rules:
- Do not only say right or wrong.
- Identify repeated patterns such as vague pronouns, comma misuse, cause/effect confusion, or weak evidence selection.
- Give specific next steps.
- Keep the tone encouraging but honest.
"""

    def _merge_report(self, base_report: Dict[str, Any], ai_report: Dict[str, Any]) -> Dict[str, Any]:
        merged = base_report.copy()
        for key in [
            "skill_breakdown",
            "strongest_skills",
            "weakest_skills",
            "error_patterns",
            "weak_knowledge_points",
            "recommended_next_practice",
            "student_summary",
            "parent_teacher_summary"
        ]:
            if ai_report.get(key):
                merged[key] = ai_report[key]
        merged["overall"] = base_report["overall"]
        return merged


_map_language_arts_service: MapLanguageArtsService | None = None


def get_map_language_arts_service() -> MapLanguageArtsService:
    global _map_language_arts_service
    if _map_language_arts_service is None:
        _map_language_arts_service = MapLanguageArtsService()
    return _map_language_arts_service
