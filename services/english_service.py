"""
英语学科服务模块
提供完形填空(cloze)和匹配题(match)两种题型的生成逻辑
"""
import random
import logging
import json
from typing import Dict, Any, List, Optional
from core.ai_generator import get_ai_generator
from services.library_admin_service import get_library_admin_service
from services.report_history_service import get_report_history_service

logger = logging.getLogger(__name__)


class EnglishService:
    """英语学科服务类"""
    
    def __init__(self):
        """初始化英语服务"""
        self.ai_generator = get_ai_generator()
        self.library_admin_service = get_library_admin_service()
        self.report_history_service = get_report_history_service()
        logger.info("EnglishService initialized")
    
    async def generate_exam(
        self,
        count: int = 10,
        library: Optional[str] = None,
        mode: str = "cloze"
    ) -> Dict[str, Any]:
        """
        生成英语考题
        
        Args:
            count: 题目数量；passage_cloze 时表示短文挖空数量
            library: 词库名称(可选，不传自动选择已启用词库)
            mode: 题型模式 (cloze/match/passage_cloze)
        
        Returns:
            包含题目列表的字典
        """
        try:
            if mode not in ["cloze", "match", "passage_cloze"]:
                return {"error": f"不支持的题型: {mode}", "questions": []}

            resolved_library = self.library_admin_service.resolve_enabled_library(
                subject="english",
                requested_library=library
            )
            all_library_words = self.library_admin_service.get_library_items(resolved_library["file_name"])
            selected_words = self.library_admin_service.get_random_library_items(resolved_library["file_name"], count)
            
            if not selected_words:
                return {
                    "error": f"Library {resolved_library['name']}.txt not found or empty",
                    "questions": []
                }
            
            words_list_str = ", ".join(selected_words)
            
            # 根据模式生成对应的 Prompt
            if mode == "passage_cloze":
                return await self._generate_passage_cloze(
                    count=count,
                    selected_words=selected_words,
                    all_library_words=all_library_words
                )
            if mode == "cloze":
                prompt = self._build_cloze_prompt(words_list_str)
            else:
                prompt = self._build_match_prompt(words_list_str)
            
            # 调用 AI 生成题目
            result = await self.ai_generator.generate_questions(prompt)
            questions = result.get("questions", [])

            # 后处理：校验答案、补足词库干扰项、减少整套题选项重复并打散顺序
            questions = self._finalize_options(questions, selected_words, all_library_words, mode)

            if not questions:
                return {"error": "AI 未返回有效题目，请稍后重试", "questions": []}

            logger.info(f"Successfully generated {len(questions)} {mode} questions")
            return {"questions": questions}
        
        except Exception as e:
            logger.error(f"Error generating exam: {str(e)}")
            return {"error": str(e), "questions": []}

    async def _generate_passage_cloze(
        self,
        count: int,
        selected_words: List[str],
        all_library_words: List[str]
    ) -> Dict[str, Any]:
        """生成一篇多空 passage cloze。"""
        allowed_counts = {5, 10, 15, 20}
        if count not in allowed_counts:
            return {"error": "Passage Cloze 仅支持 5、10、15、20 个空", "questions": []}
        if len(selected_words) < count:
            return {"error": "词库可用词不足，无法生成 Passage Cloze", "questions": []}

        target_words = selected_words[:count]
        prompt = self._build_passage_cloze_prompt(", ".join(target_words), count)
        result = await self.ai_generator.generate_json(
            prompt,
            system_message="You create student-friendly passage cloze questions. Return valid JSON only.",
            temperature=0.7
        )
        raw_question = {}
        raw_questions = result.get("questions")
        if isinstance(raw_questions, list) and raw_questions:
            raw_question = raw_questions[0]
        elif isinstance(result, dict):
            raw_question = result

        question = self._normalize_passage_cloze_question(
            raw_question=raw_question,
            target_words=target_words,
            all_library_words=all_library_words
        )
        if not question:
            return {"error": "AI 未返回有效 Passage Cloze 题目，请稍后重试", "questions": []}

        logger.info(f"Successfully generated passage_cloze with {len(question.get('cloze_items', []))} blanks")
        return {"questions": [question]}
    
    def _build_cloze_prompt(self, words: str) -> str:
        """
        构建完形填空题的 Prompt
        
        Args:
            words: 逗号分隔的词汇列表
        
        Returns:
            Prompt 字符串
        """
        return f"""
        Create one 4-option multiple choice cloze question for EACH target word: {words}.
        STRICT RULES FOR OPTIONS:
        1. Each question must have 4 different choices in 'options'.
        2. The correct answer must be the target word for that question.
        3. Distractors should be real vocabulary words and plausible, but clearly wrong in the sentence context.
        4. Prefer words from the same vocabulary library as distractors when possible.
        5. Vary the correct answer position across A/B/C/D.
        
        Requirements:
        1. 'sentence': Use a defining context. (e.g., 'A roommate you have for only a month is a ____ one.') Use '____' for the blank.
        2. 'options': 4 choices (shuffled).
        3. 'answer': Correct word.
        4. 'meaning': Chinese meaning.
        5. 'analysis': Brief explanation.
        Return JSON format: {{"questions": [...]}}
        """
    
    def _build_match_prompt(self, words: str) -> str:
        """
        构建匹配题的 Prompt
        
        Args:
            words: 逗号分隔的词汇列表
        
        Returns:
            Prompt 字符串
        """
        return f"""
        Create one word-meaning matching question for EACH target word: {words}.
        STRICT RULES FOR OPTIONS:
        1. Each question must have 4 different word choices in 'options'.
        2. The correct answer must be the target word for that question.
        3. Distractors should be real vocabulary words and semantically or morphologically plausible, but clearly not the definition's answer.
        4. Prefer words from the same vocabulary library as distractors when possible.
        5. Vary the correct answer position across A/B/C/D.
        
        FIELDS:
        - 'sentence': A clear English definition of the word (e.g., "[v.] to make something better"). 
        - 'options': 4 words (shuffled).
        - 'answer': The exact word from the options that matches the definition.
        - 'meaning': English synonyms.
        - 'analysis': One simple example sentence.
        - NO CHINESE.

        Return JSON format: {{"questions": [...]}}
        """

    def _build_passage_cloze_prompt(self, words: str, count: int) -> str:
        """构建短文多空题 Prompt。"""
        return f"""
        Create ONE short, coherent English passage using these exact target words: {words}.

        Requirements:
        1. The passage must be natural and contextually smooth.
        2. Replace each target word with a numbered blank exactly once: [[1]], [[2]], ... [[{count}]].
        3. The context around every blank must make the correct answer unique.
        4. Do not show the target words in the passage outside their blanks.
        5. Keep the passage age-appropriate and concise.
        6. Create exactly {count} cloze_items in the same order as the blanks.
        7. For each cloze item, set answer to the exact target word and write a brief explanation.
        8. You may include options, but the backend will replace distractors with words from the selected library.

        Return valid JSON only:
        {{
          "questions": [
            {{
              "sentence": "Passage with [[1]] and [[2]] blanks...",
              "answer": "passage_cloze",
              "meaning": "Passage Cloze",
              "analysis": "Read the whole passage and use context.",
              "cloze_items": [
                {{
                  "blank_id": 1,
                  "answer": "",
                  "options": [],
                  "analysis": ""
                }}
              ]
            }}
          ]
        }}
        """
    
    def _finalize_options(
        self,
        questions: List[Dict[str, Any]],
        target_words: List[str],
        all_library_words: List[str],
        mode: str
    ) -> List[Dict[str, Any]]:
        """整理选项：保留答案、补足混淆项、降低整套题重复并随机打散。"""
        target_keys = {self._option_key(word) for word in target_words}
        option_usage: Dict[str, int] = {}
        finalized: List[Dict[str, Any]] = []

        for q in questions:
            answer = self._clean_option(q.get("answer", ""))
            if not answer:
                continue

            ai_options = q.get("options") if isinstance(q.get("options"), list) else []
            cleaned_options = self._unique_options([answer] + [self._clean_option(opt) for opt in ai_options])
            distractors = [opt for opt in cleaned_options if self._option_key(opt) != self._option_key(answer)]

            fallback_pool = [
                word for word in all_library_words
                if self._option_key(word) != self._option_key(answer)
            ]
            ai_pool = [opt for opt in distractors if self._option_key(opt) != self._option_key(answer)]

            options = [answer]
            for pool in [fallback_pool, ai_pool]:
                self._append_distractors(options, pool, option_usage, answer, limit=4)
                if len(options) >= 4:
                    break

            random.shuffle(options)
            q["answer"] = answer
            q["options"] = options[:4]
            for opt in q["options"]:
                key = self._option_key(opt)
                option_usage[key] = option_usage.get(key, 0) + 1
            finalized.append(q)

        return finalized

    def _normalize_passage_cloze_question(
        self,
        raw_question: Dict[str, Any],
        target_words: List[str],
        all_library_words: List[str]
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_question, dict):
            return None

        passage = str(raw_question.get("sentence") or raw_question.get("passage") or "").strip()
        raw_items = raw_question.get("cloze_items") if isinstance(raw_question.get("cloze_items"), list) else []
        if not passage:
            passage = self._fallback_passage(target_words)

        target_by_key = {self._option_key(word): word for word in target_words}
        normalized_items: List[Dict[str, Any]] = []
        option_usage: Dict[str, int] = {}
        used_answers = set()

        for index, target_word in enumerate(target_words, start=1):
            raw_item = raw_items[index - 1] if index - 1 < len(raw_items) and isinstance(raw_items[index - 1], dict) else {}
            answer = self._clean_option(raw_item.get("answer")) or target_word
            answer = target_by_key.get(self._option_key(answer), target_word)
            used_answers.add(self._option_key(answer))

            raw_options = raw_item.get("options") if isinstance(raw_item.get("options"), list) else []
            options = [answer]
            library_pool = [
                word for word in all_library_words
                if self._option_key(word) != self._option_key(answer)
            ]
            ai_pool = [
                self._clean_option(opt) for opt in raw_options
                if self._option_key(opt) != self._option_key(answer)
            ]
            self._append_distractors(options, library_pool, option_usage, answer, limit=4)
            if len(options) < 4:
                self._append_distractors(options, ai_pool, option_usage, answer, limit=4)
            if len(options) < 4:
                return None

            random.shuffle(options)
            for opt in options:
                key = self._option_key(opt)
                option_usage[key] = option_usage.get(key, 0) + 1

            normalized_items.append({
                "blank_id": index,
                "answer": answer,
                "options": options[:4],
                "analysis": str(raw_item.get("analysis") or f"Context points to '{answer}'.").strip()
            })

        for index, answer in enumerate(target_words, start=1):
            pattern = f"[[{index}]]"
            if pattern not in passage:
                passage = passage.replace(answer, pattern, 1)
        if not all(f"[[{index}]]" in passage for index in range(1, len(target_words) + 1)):
            passage = self._fallback_passage(target_words)

        return {
            "sentence": passage,
            "options": [],
            "answer": "passage_cloze",
            "meaning": "Passage Cloze",
            "analysis": str(raw_question.get("analysis") or "Use context across the passage to choose each word.").strip(),
            "cloze_items": normalized_items
        }

    def _fallback_passage(self, target_words: List[str]) -> str:
        blanks = " ".join(f"[[{index}]]" for index, _ in enumerate(target_words, start=1))
        return (
            "Read the passage carefully and choose the best word for each blank. "
            f"The key vocabulary appears in this order: {blanks}."
        )

    def _append_distractors(
        self,
        options: List[str],
        candidates: List[str],
        option_usage: Dict[str, int],
        answer: str,
        limit: int = 4
    ) -> None:
        unique_candidates = self._unique_options([self._clean_option(x) for x in candidates])
        random.shuffle(unique_candidates)
        unique_candidates.sort(
            key=lambda x: (
                option_usage.get(self._option_key(x), 0),
                -self._distractor_score(answer, x)
            )
        )

        for candidate in unique_candidates:
            key = self._option_key(candidate)
            if len(options) >= limit:
                return
            if not candidate or key == self._option_key(answer):
                continue
            if any(self._option_key(existing) == key for existing in options):
                continue
            options.append(candidate)

    def _clean_option(self, value: Any) -> str:
        return str(value).strip() if value is not None else ""

    def _option_key(self, value: Any) -> str:
        return self._clean_option(value).lower()

    def _unique_options(self, values: List[str]) -> List[str]:
        seen = set()
        result: List[str] = []
        for value in values:
            cleaned = self._clean_option(value)
            key = self._option_key(cleaned)
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    def _distractor_score(self, answer: str, candidate: str) -> float:
        """给词库干扰项打分，优先选择词形更接近、没那么一眼排除的词。"""
        answer_key = self._option_key(answer)
        candidate_key = self._option_key(candidate)
        if not answer_key or not candidate_key:
            return 0

        score = 0.0
        length_gap = abs(len(answer_key) - len(candidate_key))
        score += max(0, 6 - length_gap)
        if answer_key[0] == candidate_key[0]:
            score += 3
        if len(answer_key) > 2 and len(candidate_key) > 2 and answer_key[-2:] == candidate_key[-2:]:
            score += 3
        if len(answer_key) > 3 and len(candidate_key) > 3 and answer_key[:2] == candidate_key[:2]:
            score += 2
        if "-" in answer_key and "-" in candidate_key:
            score += 1
        return score
    
    async def get_library_list(self, mode: Optional[str] = None) -> List[str]:
        """
        获取可用且已启用的词库列表

        Args:
            mode: 题型模式（cloze/match，可选）

        Returns:
            词库名称列表
        """
        return self.library_admin_service.get_enabled_library_names(subject="english")
    
    async def get_library_info(self, library_name: str) -> Dict[str, Any]:
        """
        获取指定词库的详细信息（仅已启用词库）
        
        Args:
            library_name: 词库名称
        
        Returns:
            词库信息字典
        """
        resolved = self.library_admin_service.resolve_enabled_library(
            subject="english",
            requested_library=library_name
        )
        return self.library_admin_service.get_public_library_info(resolved["file_name"])

    async def grade_exam(self, submit_data: Any) -> Dict[str, Any]:
        """
        批改考试并生成总结
        
        Args:
            submit_data: 包含题目和答案的数据
            
        Returns:
            批改结果和总结
        """
        questions = submit_data.questions
        answers = submit_data.answers
        mode = submit_data.mode
        
        if mode == "passage_cloze":
            results, correct_count = self._grade_passage_cloze(questions, answers)
        else:
            results = []
            correct_count = 0

            # 建立索引映射
            answer_map = {a.question_index: a.user_answer for a in answers}

            for i, q in enumerate(questions):
                user_ans = answer_map.get(i, "")
                is_correct = (user_ans.strip().lower() == q.answer.strip().lower())
                if is_correct:
                    correct_count += 1

                results.append({
                    "question_index": i,
                    "is_correct": is_correct,
                    "user_answer": user_ans,
                    "correct_answer": q.answer,
                    "word": q.answer,
                    "analysis": q.analysis
                })

        total_count = len(questions)
        if mode == "passage_cloze":
            total_count = len(results)
        score = (correct_count / total_count * 100) if total_count > 0 else 0
        
        # 调用 AI 生成总结
        summary_prompt = self._build_summary_prompt(results, mode, score)
        summary_result = await self.ai_generator.generate_questions(summary_prompt)
        summary = summary_result.get("summary", "Keep practicing!")
        
        response = {
            "score": score,
            "total_count": total_count,
            "correct_count": correct_count,
            "results": results,
            "summary": summary
        }
        self.report_history_service.add_report({
            "module": "word_palace",
            "module_label": "Word Palace",
            "title": f"Word Palace - {mode}",
            "mode": mode,
            "score": score,
            "total_count": total_count,
            "correct_count": correct_count,
            "summary": summary,
            "details": {
                "results": results[:50],
                "wrong_words": [r for r in results if not r.get("is_correct")][:50]
            }
        })
        return response

    def _grade_passage_cloze(self, questions: List[Any], answers: List[Any]) -> tuple[List[Dict[str, Any]], int]:
        """按 Passage Cloze 的每个空独立批改。"""
        if not questions:
            return [], 0

        answer_map = {a.question_index: a.user_answer for a in answers}
        raw_answer = answer_map.get(0, "{}")
        try:
            parsed_answers = json.loads(raw_answer) if isinstance(raw_answer, str) else raw_answer
        except json.JSONDecodeError:
            parsed_answers = {}
        if not isinstance(parsed_answers, dict):
            parsed_answers = {}

        question = questions[0]
        cloze_items = question.cloze_items or []
        results: List[Dict[str, Any]] = []
        correct_count = 0

        for item in cloze_items:
            blank_id = int(item.get("blank_id") or len(results) + 1)
            correct_answer = self._clean_option(item.get("answer", ""))
            user_answer = self._clean_option(
                parsed_answers.get(str(blank_id), parsed_answers.get(blank_id, ""))
            )
            is_correct = user_answer.lower() == correct_answer.lower()
            if is_correct:
                correct_count += 1
            results.append({
                "question_index": blank_id - 1,
                "blank_id": blank_id,
                "is_correct": is_correct,
                "user_answer": user_answer,
                "correct_answer": correct_answer,
                "word": correct_answer,
                "analysis": item.get("analysis") or question.analysis or ""
            })

        return results, correct_count

    def _build_summary_prompt(self, results: List[Dict[str, Any]], mode: str, score: float) -> str:
        """构建总结 Prompt"""
        perf_data = []
        for r in results:
            perf_data.append(f"Q: {r['is_correct']}(User: {r['user_answer']}, Correct: {r['correct_answer']})")
            
        return f"""
        Based on the English {mode} test results, provide a brief, encouraging study summary in Chinese.
        Score: {score}/100
        Details: {'; '.join(perf_data[:10])}...
        
        Requirements:
        1. Identify strengths or weaknesses.
        2. Give advice for next steps.
        3. Tone: Professional and encouraging.
        4. Return JSON format: {{"summary": "your summary text here"}}
        """
