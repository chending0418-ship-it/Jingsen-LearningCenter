"""
AI 生成器模块
封装 OpenAI API 调用逻辑，提供统一的内容生成接口
"""
import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI
from config import config

logger = logging.getLogger(__name__)


class AIGenerator:
    """AI 内容生成器类"""
    
    def __init__(self):
        """初始化 OpenAI 客户端"""
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.fix_base_url()
        )
        self.model = config.MODEL_NAME
        logger.info(f"AIGenerator initialized with model: {self.model}")
    
    async def generate_questions(
        self,
        prompt: str,
        system_message: str = "You are a teacher. Output valid JSON only.",
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成题目内容
        
        Args:
            prompt: 用户提示词
            system_message: 系统消息
            temperature: 生成温度(0-1)
            **kwargs: 其他 OpenAI API 参数
        
        Returns:
            包含题目列表的字典
        
        Raises:
            Exception: API 调用失败时抛出异常
        """
        try:
            logger.info(f"Generating questions with prompt length: {len(prompt)}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                **kwargs
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            
            # 兼容不同的返回格式
            questions = data.get("questions", data.get("results", []))
            
            # 如果获取的是空数组，尝试直接处理 data
            if not questions and isinstance(data, list):
                questions = data
            
            logger.info(f"Successfully generated {len(questions)} questions")
            return {"questions": questions}
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            raise Exception(f"Failed to parse AI response: {str(e)}")
        
        except Exception as e:
            logger.error(f"AI generation error: {str(e)}")
            raise Exception(f"AI generation failed: {str(e)}")
    
    async def generate_json(
        self,
        prompt: str,
        system_message: str = "You are a teacher. Output valid JSON only.",
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """生成并返回完整 JSON 对象，适用于题目以外的结构化结果。"""
        try:
            logger.info(f"Generating JSON with prompt length: {len(prompt)}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                **kwargs
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("AI response is not a JSON object")
            logger.info("Successfully generated JSON content")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            raise Exception(f"Failed to parse AI response: {str(e)}")
        except Exception as e:
            logger.error(f"AI JSON generation error: {str(e)}")
            raise Exception(f"AI JSON generation failed: {str(e)}")

    async def generate_content(
        self,
        prompt: str,
        system_message: str = "You are a helpful assistant.",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        生成通用文本内容
        
        Args:
            prompt: 用户提示词
            system_message: 系统消息
            temperature: 生成温度
            max_tokens: 最大令牌数
        
        Returns:
            生成的文本内容
        """
        try:
            params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature
            }
            
            if max_tokens:
                params["max_tokens"] = max_tokens
            
            response = self.client.chat.completions.create(**params)
            content = response.choices[0].message.content
            
            logger.info("Successfully generated text content")
            return content
        
        except Exception as e:
            logger.error(f"Content generation error: {str(e)}")
            raise Exception(f"Content generation failed: {str(e)}")


# 全局 AI 生成器实例(单例模式)
_ai_generator_instance: Optional[AIGenerator] = None


def get_ai_generator() -> AIGenerator:
    """
    获取 AI 生成器实例(单例)
    
    Returns:
        AIGenerator 实例
    """
    global _ai_generator_instance
    if _ai_generator_instance is None:
        _ai_generator_instance = AIGenerator()
    return _ai_generator_instance
