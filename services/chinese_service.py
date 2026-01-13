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
                    # 这里的 result["questions"] 应该包含 4 个小题，作为一个大组返回
                    questions.extend(result.get("questions", []))
            else:
                # 随机抽取成语，每 4 个一组
                all_idioms = self._get_random_items("chinese_idioms", count * 4)
                for i in range(0, len(all_idioms), 4):
                    group = all_idioms[i:i+4]
                    if len(group) < 4: break
                    
                    prompt = self._build_idiom_fill_prompt(",".join(group))
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
        2. 创建四个句子，每句话都有一个空格（用'____'表示）。
        3. 每句话必须且仅能填入这四个词中的一个，每个词只能用一次。
        4. 语义必须严谨，确保唯一答案。
        
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
        请使用以下四个成语：{idioms} 创作一个成语填空题。
        
        规则：
        1. 写一段连贯的话（约100-200字）。
        2. 这段话中有四个空格（分别用'(1)____', '(2)____', '(3)____', '(4)____'表示）。
        3. 每个成语对应一个空格，确保语义逻辑唯一。
        
        返回格式 JSON:
        {{
            "questions": [
                {{
                    "sentence": "整段话的内容",
                    "options": ["成语1", "成语2", "成语3", "成语4"],
                    "answer": "(1)成语A, (2)成语B, (3)成语C, (4)成语D",
                    "analysis": "成语在语境中的用法说明"
                }}
            ]
        }}
        """

    async def grade_exam(self, submit_data: Any) -> Dict[str, Any]:
        """批改并总结"""
        # 复用逻辑或自定义
        return {"message": "Chinese grading logic here"}
