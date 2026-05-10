"""
英语学科服务模块
提供完形填空(cloze)和匹配题(match)两种题型的生成逻辑
"""
import random
import logging
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
            count: 题目数量
            library: 词库名称(可选，不传自动选择已启用词库)
            mode: 题型模式 (cloze/match)
        
        Returns:
            包含题目列表的字典
        """
        try:
            if mode not in ["cloze", "match"]:
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
            if mode == "cloze":
                prompt = self._build_cloze_prompt(words_list_str)
            else:
                prompt = self._build_match_prompt(words_list_str)
            
            # 调用 AI 生成题目
            result = await self.ai_generator.generate_questions(prompt)
            questions = result.get("questions", [])

            # 后处理：校验答案、补足混淆项、减少整套题选项重复并打散顺序
            questions = self._finalize_options(questions, selected_words, all_library_words, mode)

            if not questions:
                return {"error": "AI 未返回有效题目，请稍后重试", "questions": []}

            logger.info(f"Successfully generated {len(questions)} {mode} questions")
            return {"questions": questions}
        
        except Exception as e:
            logger.error(f"Error generating exam: {str(e)}")
            return {"error": str(e), "questions": []}
    
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
        3. Distractors should be plausible but clearly wrong in the sentence context.
        4. Distractors should NOT simply be other target words from this same list unless they are genuinely confusing.
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
        3. Distractors should be semantically or morphologically plausible, but clearly not the definition's answer.
        4. Distractors should NOT simply be other target words from this same list unless they are genuinely confusing.
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

            non_target_ai = [opt for opt in distractors if self._option_key(opt) not in target_keys]
            target_ai = [opt for opt in distractors if self._option_key(opt) in target_keys]
            non_target_pool = [
                word for word in all_library_words
                if self._option_key(word) not in target_keys and self._option_key(word) != self._option_key(answer)
            ]
            fallback_pool = [
                word for word in all_library_words
                if self._option_key(word) != self._option_key(answer)
            ]

            options = [answer]
            for pool in [non_target_ai, non_target_pool, target_ai, fallback_pool]:
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
        unique_candidates.sort(key=lambda x: option_usage.get(self._option_key(x), 0))

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
                "analysis": q.analysis
            })
            
        total_count = len(questions)
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
                "results": results[:50]
            }
        })
        return response

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
