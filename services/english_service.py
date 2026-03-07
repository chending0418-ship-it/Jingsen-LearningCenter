"""
英语学科服务模块
提供完形填空(cloze)和匹配题(match)两种题型的生成逻辑
"""
import random
import logging
from typing import Dict, Any, List
from core.ai_generator import get_ai_generator
from core.vocabulary import get_vocabulary_manager

logger = logging.getLogger(__name__)


class EnglishService:
    """英语学科服务类"""
    
    def __init__(self):
        """初始化英语服务"""
        self.ai_generator = get_ai_generator()
        self.vocab_manager = get_vocabulary_manager()
        logger.info("EnglishService initialized")
    
    async def generate_exam(
        self,
        count: int = 10,
        library: str = "4000-202603",
        mode: str = "cloze"
    ) -> Dict[str, Any]:
        """
        生成英语考题
        
        Args:
            count: 题目数量
            library: 词库名称
            mode: 题型模式 (cloze/match)
        
        Returns:
            包含题目列表的字典
        """
        try:
            # 获取随机词汇
            selected_words = self.vocab_manager.get_random_words(library, count)
            
            if not selected_words:
                return {
                    "error": f"Library {library}.txt not found or empty",
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
            
            # 后处理：打散选项顺序
            questions = self._shuffle_options(questions)
            
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
        Create 4-option multiple choice questions for: {words}.
        STRICT RULES FOR OPTIONS:
        1. Each question must have 4 different choices in 'options'.
        2. DO NOT always put the correct answer at index 0. You MUST shuffle the correct word's position (A, B, C, or D) randomly for EACH question.
        
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
        Create word-meaning matching questions for: {words}.
        STRICT RULES FOR OPTIONS:
        1. Each question must have 4 different word choices in 'options'.
        2. DO NOT always put the correct answer at index 0. You MUST shuffle the correct word's position (A, B, C, or D) randomly for EACH question.
        3. For example, in question 1 the answer can be B, in question 2 it can be D, in question 3 it can be A.
        
        FIELDS:
        - 'sentence': A clear English definition of the word (e.g., "[v.] to make something better"). 
        - 'options': 4 words (shuffled).
        - 'answer': The exact word from the options that matches the definition.
        - 'meaning': English synonyms.
        - 'analysis': One simple example sentence.
        - NO CHINESE.

        Return JSON format: {{"questions": [...]}}
        """
    
    def _shuffle_options(self, questions: List[Dict]) -> List[Dict]:
        """
        打散题目选项顺序，确保正确答案位置随机
        
        Args:
            questions: 题目列表
        
        Returns:
            处理后的题目列表
        """
        for q in questions:
            if "options" in q and "answer" in q:
                # 确保正确答案在选项中
                if q["answer"] not in q["options"]:
                    q["options"].append(q["answer"])
                
                # 去重
                unique_options = list(dict.fromkeys(q["options"]))
                
                # 如果选项多于4个，保留正确答案并随机抽取其他选项
                if len(unique_options) > 4:
                    correct_ans = q["answer"]
                    distractors = [o for o in unique_options if o != correct_ans]
                    unique_options = [correct_ans] + random.sample(distractors, 3)
                
                # 随机打乱
                random.shuffle(unique_options)
                q["options"] = unique_options
        
        return questions
    
    async def get_library_list(self) -> List[str]:
        """
        获取可用的词库列表
        
        Returns:
            词库名称列表
        """
        return self.vocab_manager.get_all_libraries()
    
    async def get_library_info(self, library_name: str) -> Dict[str, Any]:
        """
        获取指定词库的详细信息
        
        Args:
            library_name: 词库名称
        
        Returns:
            词库信息字典
        """
        return self.vocab_manager.get_library_info(library_name)

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
        
        return {
            "score": score,
            "total_count": total_count,
            "correct_count": correct_count,
            "results": results,
            "summary": summary
        }

    def _build_summary_prompt(self, results: List[Dict], mode: str, score: float) -> str:
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
