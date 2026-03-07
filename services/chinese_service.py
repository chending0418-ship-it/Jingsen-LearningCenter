"""
语文学科服务模块
提供词语辨析和关联词填空两种题型的生成逻辑
"""
import random
import logging
from typing import Dict, Any, List, Optional
from core.ai_generator import get_ai_generator
from core.vocabulary import get_vocabulary_manager
from services.library_admin_service import get_library_admin_service

logger = logging.getLogger(__name__)


class ChineseService:
    """语文学科服务类"""
    
    def __init__(self):
        """初始化语文服务"""
        self.ai_generator = get_ai_generator()
        self.vocab_manager = get_vocabulary_manager()
        self.library_admin_service = get_library_admin_service()
        logger.info("ChineseService initialized")
    
    async def generate_exam(
        self,
        count: int = 5,
        library: Optional[str] = None,
        mode: str = "word_discrim"
    ) -> Dict[str, Any]:
        """
        生成语文考题
        
        Args:
            count: 题目数量
            library: 词库名称(可选，不传自动选择已启用词库)
            mode: 题型模式 (word_discrim: 词语辨析, conj_fill: 关联词填空, idiom_fill: 成语填空)
        
        Returns:
            包含题目列表的字典
        """
        try:
            questions = []
            mode_to_library_type = {
                "word_discrim": "word_discrim",
                "conj_fill": "conj_fill",
                "idiom_fill": "idiom_fill"
            }

            if mode not in mode_to_library_type:
                return {"error": f"不支持的题型: {mode}", "questions": []}

            resolved_library = self.library_admin_service.resolve_enabled_library(
                subject="chinese",
                requested_library=library,
                library_type=mode_to_library_type[mode]
            )
            selected_library = resolved_library["file_name"]

            if mode == "word_discrim":
                core_words = self._get_random_items(selected_library, count)
                if not core_words:
                    return {"error": f"词库 {resolved_library['name']} 为空或不可用", "questions": []}
                for word in core_words:
                    prompt = self._build_word_discrim_prompt(word)
                    result = await self.ai_generator.generate_questions(prompt)
                    questions.extend(result.get("questions", []))
            elif mode == "conj_fill":
                conjunctions = self._get_random_items(selected_library, count)
                if not conjunctions:
                    return {"error": f"词库 {resolved_library['name']} 为空或不可用", "questions": []}
                for conj in conjunctions:
                    prompt = self._build_conj_fill_prompt(conj, conjunctions)
                    result = await self.ai_generator.generate_questions(prompt)
                    for q in result.get("questions", []):
                        q["options"] = conjunctions
                    questions.extend(result.get("questions", []))
            elif mode == "idiom_fill":
                for _ in range(count):
                    all_idioms = self._get_random_items(selected_library, 4)
                    if len(all_idioms) < 4:
                        return {"error": f"词库 {resolved_library['name']} 词条不足，至少需要 4 条", "questions": []}
                    prompt = self._build_idiom_fill_prompt(",".join(all_idioms))
                    result = await self.ai_generator.generate_questions(prompt)
                    questions.extend(result.get("questions", []))

            if not questions:
                return {"error": "AI 未返回有效题目，请稍后重试", "questions": []}

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

    def _build_conj_fill_prompt(self, correct_conj: str, all_options: List[str]) -> str:
        """构建关联词填空题的 Prompt"""
        options_str = "、".join(all_options)
        return f"""
        作为一个小学五年级的高级语文老师，请使用关联词“{correct_conj}”创作一道填空题。
        
        规则：
        1. 关联词：{correct_conj}。
        2. 备选池：{options_str}。
        3. 任务：创作一个句子，将“{correct_conj}”中的词语部分（以“……”分隔）分别替换为“____”。
           - 重要：如果关联词是成对的（如“虽然……但是”），句子中必须且只能出现两个“____”。
           - 重要：如果关联词是单体的（目前词库暂无），则出现一个“____”。
           - 示例：如果关联词是“虽然……但是”，句子应为“____天气很冷，____小明还是坚持去上学。”
        4. 语法与语序要求（非常重要）：
           - 确保句子的语序符合地道的中文表达。
           - 关联词的位置要准确。如果前后分句主语相同，主语通常放在第一个关联词之前（例如：小明____学习好，____体育也很好）；如果主语不同，关联词通常放在主语之前。
           - 严禁出现“不仅小明……还他……”这种啰嗦且不规范的表述。
        5. 语义严谨：确保在备选池中，只有“{correct_conj}”是唯一最准确、逻辑最通顺的答案。
        
        返回格式 JSON:
        {{
            "questions": [
                {{
                    "sentence": "生成的句子内容",
                    "answer": "{correct_conj}",
                    "analysis": "从逻辑关系（转折、递进、因果等）角度详细解释为什么这里应该用这个关联词"
                }}
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

    async def get_library_list(self, mode: Optional[str] = None) -> List[str]:
        """获取语文可用且已启用的词库列表"""
        mode_to_library_type = {
            "word_discrim": "word_discrim",
            "conj_fill": "conj_fill",
            "idiom_fill": "idiom_fill"
        }
        library_type = mode_to_library_type.get(mode) if mode else None
        return self.library_admin_service.get_enabled_library_names(subject="chinese", library_type=library_type)

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
            # 兼容各种填空的答案对比
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
