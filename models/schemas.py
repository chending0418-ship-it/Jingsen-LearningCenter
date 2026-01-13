"""
数据模型定义
使用 Pydantic 定义请求和响应的数据模型
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class QuestionItem(BaseModel):
    """单个题目数据模型"""
    sentence: str = Field(..., description="题目句子或定义")
    options: List[str] = Field(..., description="选项列表")
    answer: str = Field(..., description="正确答案")
    meaning: Optional[str] = Field(None, description="词义或解释")
    analysis: Optional[str] = Field(None, description="答案解析")


class QuestionsResponse(BaseModel):
    """题目生成响应模型"""
    questions: List[QuestionItem] = Field(..., description="题目列表")
    total: Optional[int] = Field(None, description="题目总数")
    subject: Optional[str] = Field(None, description="学科名称")
    mode: Optional[str] = Field(None, description="题型模式")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(None, description="详细信息")


class GenerateRequest(BaseModel):
    """题目生成请求模型"""
    count: int = Field(10, ge=1, le=50, description="题目数量")
    library: Optional[str] = Field("book123", description="词库名称")
    mode: Optional[Literal["cloze", "match"]] = Field("cloze", description="题型模式")
    difficulty: Optional[Literal["easy", "medium", "hard"]] = Field("medium", description="难度级别")


class LibraryInfo(BaseModel):
    """词库信息模型"""
    name: str = Field(..., description="词库名称")
    total_words: int = Field(..., description="词汇总数")
    is_cached: bool = Field(..., description="是否已缓存")
    file_path: str = Field(..., description="文件路径")


class AnswerItem(BaseModel):
    """用户提交的单个答案"""
    question_index: int = Field(..., description="题目索引")
    user_answer: str = Field(..., description="用户选择的答案")


class SubmitRequest(BaseModel):
    """提交答案请求模型"""
    questions: List[QuestionItem] = Field(..., description="原始题目列表")
    answers: List[AnswerItem] = Field(..., description="用户答案列表")
    mode: str = Field("cloze", description="题型模式")


class GradeResult(BaseModel):
    """批改结果数据模型"""
    question_index: int
    is_correct: bool
    user_answer: str
    correct_answer: str
    analysis: Optional[str]


class GradeResponse(BaseModel):
    """批改和总结响应模型"""
    score: float = Field(..., description="得分")
    total_count: int = Field(..., description="总题数")
    correct_count: int = Field(..., description="正确数")
    results: List[GradeResult] = Field(..., description="逐题批改结果")
    summary: str = Field(..., description="学习总结")
