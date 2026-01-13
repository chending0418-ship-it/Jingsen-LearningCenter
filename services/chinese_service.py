"""
语文学科服务模块
提供词语辨析和成语填空两种题型的生成逻辑
"""
import random
import logging
from typing import Dict, Any, List
from core.ai_generator import get_ai_generator
from core.vocabulary import get_vocabulary_manager

logger = logging.getLogger(__name__)


class ChineseService:
    """语文学科服务类"""
    
    def __init__(self):
        """初始化语文服务"""
        self.ai_generator = get_ai_generator()
        self.vocab_manager = get_vocabulary_manager()
        logger.info("ChineseService initialized")
    
    async def generate_exam(
        self,
        count: int = 5,
        library: str = "chinese_words",
        mode: str = "word_discrim"
    ) -> Dict[str, Any]:
        """
        生成语文考题
        
        Args:
            count: 题目数量
            library: 词库名称
            mode: 题型模式 (word_discrim: 词语辨析, idiom_fill: 成语填空)
        
        Returns:
            包含题目列表的字典
        """
        try:
            questions = []
            
            if mode == "word_discrim":
                # 随机抽取核心词
                core_words = self._get_random_items("chinese_words", count)
                for word in core_words:
                    prompt = self._build_word_discrim_prompt(word)
                    result = await self.ai_generator.generate_questions(prompt)
                    questions.extend(result.get("questions", []))
            else:
                # 随机抽取成语，确保 count 组题目使用完全不同的成语
                # 每次调用 API 生成一组，所以这里循环 count 次
                for _ in range(count):
                    # 获取当前已使用的成语，防止重复（简单实现：从词库重新抽）
                    # 注意：为了绝对不重复，这里应该传入已使用的列表，
                    # 但目前 generate_exam 是被 API 分次调用的，我们需要在前端或 service 维护状态
                    # 这里的改进是：在 Prompt 中强调严谨性
                    all_idioms = self._get_random_items("chinese_idioms", 4)
                    prompt = self._build_idiom_fill_prompt(",".join(all_idioms))
                    result = await self.ai_generator.generate_questions(prompt)
                    questions.extend(result.get("questions", []))
            
            logger.info(f"Successfully generated {len(questions)} {mode} questions")
            return {"questions": questions}
        
        except Exception as e:
            logger.error(f"Error generating Chinese exam: {str(e)}")
            return {"error": str(e), "questions": []}
    
    def _get_random_items(self, library: str, count: int) -> List[str]:
        """从词库中随机获取指定数量的单项"""
        file_path = f"data/{library}.txt"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                items = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            
            if not items:
                return []
                
            return random.sample(items, min(count, len(items)))
        except Exception as e:
            logger.error(f"Error reading {library}: {str(e)}")
            return []

    def _build_word_discrim_prompt(self, core_word: str) -> str:
        """构建词语辨析题的 Prompt"""
        return f"""
        作为一个小学五年级的语文老师，请以“{core_word}”为核心词，出一道词语辨析填空题。
        
        规则：
        1. 核心词：{core_word}。请另外扩充三个与之意思相近但有细微差别的词作为备选。
        2. 重要：这三个扩充词必须也是两个字的，与“{core_word}”保持一致。
        3. 创建四个句子，每句话都有一个空格（用'____'表示）。
        4. 每句话必须且仅能填入这四个词中的一个，每个词只能用一次。
        5. 语义必须严谨，确保唯一答案。
        
        返回格式 JSON:
        {{
            "questions": [
                {{
                    "sentence": "句子内容1",
                    "options": ["{core_word}", "扩充词1", "扩充词2", "扩充词3"],
                    "answer": "正确词",
                    "analysis": "这四个词的细微辨析说明"
                }},
                ... (共4小题，分别对应这四个词)
            ]
        }}
        """

    def _build_idiom_fill_prompt(self, idioms: str) -> str:
        """构建成语填空题的 Prompt"""
        return f"""
        请使用以下四个成语：{idioms} 创作一个高质量、语义严谨的成语填空题。
        
        规则：
        1. 创作一段连贯、有文学色彩的短文（约150字）。
        2. 严谨性要求：成语的使用必须符合规范，不得出现生硬凑数或语义不通的情况。
           - 错误示例：不要写出“小明加入了津津有味的队伍”这种逻辑错误的句子。
           - 正确示例：应确保成语与上下文动作、环境、情感完美契合。
        3. 这段短文中有四个空格（分别用'(1)____', '(2)____', '(3)____', '(4)____'表示）。
        4. 每个成语对应一个空格，确保语义逻辑唯一。
        
        返回格式 JSON:
        {{
            "questions": [
                {{
                    "sentence": "整段话的内容",
                    "options": ["成语1", "成语2", "成语3", "成语4"],
                    "answer": "(1)成语A, (2)成语B, (3)成语C, (4)成语D",
                    "analysis": "每个成语在语境中的详细用法说明"
                }}
            ]
        }}
        """

    async def grade_exam(self, submit_data: Any) -> Dict[str, Any]:
        """批改考试并生成总结"""
        questions = submit_data.questions
        answers = submit_data.answers
        mode = submit_data.mode
        
        results = []
        correct_count = 0
        
        # 建立索引映射
        answer_map = {a.question_index: a.user_answer for a in answers}
        
        for i, q in enumerate(questions):
            user_ans = answer_map.get(i, "")
            # 兼容成语填空的子答案对比
            correct_ans = getattr(q, 'subAnswer', getattr(q, 'answer', ""))
            
            is_correct = (user_ans.strip() == correct_ans.strip())
            if is_correct:
                correct_count += 1
            
            results.append({
                "question_index": i,
                "is_correct": is_correct,
                "user_answer": user_ans,
                "correct_answer": correct_ans,
                "analysis": getattr(q, 'analysis', "")
            })
            
        total_count = len(questions)
        score = (correct_count / total_count * 100) if total_count > 0 else 0
        
        # 调用 AI 生成总结
        perf_data = []
        for r in results:
            perf_data.append(f"Q: {r['is_correct']}(User: {r['user_answer']}, Correct: {r['correct_answer']})")
            
        summary_prompt = f"""
        基于以下语文{mode}测试结果，提供一个简短的、鼓励性的中文学习总结。
        得分: {score}/100
        详情: {'; '.join(perf_data[:10])}...
        
        要求：
        1. 指出优点或不足。
        2. 给出下一步学习建议。
        3. 语气：专业且富有鼓励性。
        返回 JSON 格式: {{"summary": "总结内容"}}
        """
        
        summary_result = await self.ai_generator.generate_questions(summary_prompt)
        summary = summary_result.get("summary", "练习完成，继续加油！")
        
        return {
            "score": score,
            "total_count": total_count,
            "correct_count": correct_count,
            "results": results,
            "summary": summary
        }
