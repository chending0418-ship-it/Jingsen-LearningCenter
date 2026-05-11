"""
数据模型定义
使用 Pydantic 定义请求和响应的数据模型
"""
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union, Literal


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
    library: Optional[str] = Field("4000-202603", description="词库名称")
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


class LibraryAdminItem(BaseModel):
    """后台词库条目"""
    id: str = Field(..., description="词库ID")
    subject: Literal["english", "chinese"] = Field(..., description="学科")
    name: str = Field(..., description="词库名称")
    file_name: str = Field(..., description="文件名(不含扩展名)")
    enabled: bool = Field(..., description="是否启用")
    library_type: Optional[str] = Field(None, description="词库用途类型")
    total_items: int = Field(0, description="词条数量")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class LibraryListResponse(BaseModel):
    """词库列表响应"""
    libraries: List[LibraryAdminItem] = Field(..., description="词库列表")
    total: int = Field(..., description="总数")


class LibraryDetailResponse(LibraryAdminItem):
    """词库详情响应"""
    items: List[str] = Field(default_factory=list, description="词条列表")


class LibraryCreateRequest(BaseModel):
    """新建词库请求"""
    subject: Literal["english", "chinese"] = Field(..., description="学科")
    name: str = Field(..., min_length=1, description="词库名称")
    items: List[str] = Field(default_factory=list, description="词条列表")
    enabled: bool = Field(True, description="是否启用")
    library_type: Optional[str] = Field(None, description="词库用途类型")


class LibraryUpdateRequest(BaseModel):
    """更新词库元信息请求"""
    name: Optional[str] = Field(None, min_length=1, description="词库名称")
    library_type: Optional[str] = Field(None, description="词库用途类型")


class LibraryStatusRequest(BaseModel):
    """更新词库启用状态请求"""
    enabled: bool = Field(..., description="是否启用")


class LibraryItemsUpdateRequest(BaseModel):
    """更新词条请求"""
    items: List[str] = Field(default_factory=list, description="词条列表")


MapLanguageArtsDifficulty = Literal["easy", "medium", "hard", "adaptive"]


class MapLanguageArtsSkill(BaseModel):
    """MAP Language Arts 技能元数据"""
    key: str
    title: str
    cn: str
    summary: str
    question_types: List[str] = Field(default_factory=list)
    subskills: List[str] = Field(default_factory=list)


class MapLanguageArtsGenerateRequest(BaseModel):
    """MAP Language Arts 生成请求"""
    skill_area: str = Field("grammar_usage", description="兼容旧版目标技能字段")
    grade_level: str = Field("Grade 6", description="年级，例如 Grade 6")
    topic: Optional[str] = Field(None, description="Topic，例如 Grammar and mechanics")
    skill: Optional[str] = Field(None, description="Skill，例如 Spelling")
    difficulty: MapLanguageArtsDifficulty = Field("medium", description="难度")
    question_count: int = Field(10, ge=1, le=20, description="题目数量")
    option_count: int = Field(4, ge=4, le=5, description="选项数量")
    include_explanation: bool = Field(True, description="是否包含解析")
    subskill_focus: Optional[str] = Field(None, description="具体薄弱 Detail，例如 vague pronouns 或 capitalization in letters")
    detail_focus: Optional[str] = Field(None, description="后端专项训练用 Detail 文本，兼容 Vocabulary Skills 的聚焦字段")
    detail_ids: List[str] = Field(default_factory=list, description="可选：指定 detail id；默认按 grade/topic/skill 自动覆盖多个 detail")


class MapLanguageArtsQuestion(BaseModel):
    """MAP Language Arts 题目"""
    question_id: int
    skill_area: str
    topic: Optional[str] = None
    skill: Optional[str] = None
    detail: Optional[str] = None
    subskill: str
    difficulty: str
    question_stem: str
    passage_or_sentence: str
    answer_choices: Dict[str, str]
    correct_answer: Union[str, List[str]]
    explanation: Optional[str] = None
    common_error_tested: Optional[str] = None


class MapLanguageArtsGenerateResponse(BaseModel):
    """MAP Language Arts 生成响应"""
    test_title: str = "MAP Language Arts Practice"
    grade_level: str
    skill_area: str
    difficulty: str
    question_count: int
    questions: List[MapLanguageArtsQuestion]


class MapLanguageArtsAnswerItem(BaseModel):
    """MAP Language Arts 单题作答"""
    question_id: int
    student_answer: Union[str, List[str]]


class MapLanguageArtsEvaluateRequest(BaseModel):
    """MAP Language Arts 评估请求"""
    questions: List[MapLanguageArtsQuestion]
    answers: List[MapLanguageArtsAnswerItem]


class MapLanguageArtsEvaluationResponse(BaseModel):
    """MAP Language Arts 评估响应"""
    overall: Dict[str, Any]
    skill_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    strongest_skills: List[str] = Field(default_factory=list)
    weakest_skills: List[str] = Field(default_factory=list)
    error_patterns: List[str] = Field(default_factory=list)
    weak_knowledge_points: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_next_practice: List[Dict[str, Any]] = Field(default_factory=list)
    student_summary: str = ""
    parent_teacher_summary: str = ""
    results: List[Dict[str, Any]] = Field(default_factory=list)


VocabularySkillsDifficulty = Literal["easy", "medium", "hard", "adaptive"]


class VocabularySkillsGenerateRequest(BaseModel):
    """Word Palace Vocabulary Skills 生成请求"""
    grade_level: str = Field("Grade 6", description="年级，例如 Grade 6")
    topic: Optional[str] = Field("Vocabulary", description="Topic，例如 Vocabulary")
    skill: str = Field(..., description="Skill，例如 Prefixes and suffixes")
    detail_focus: Optional[str] = Field(None, description="后端专项训练用 Detail 文本，不直接作为学生选择项")
    difficulty: VocabularySkillsDifficulty = Field("medium", description="难度")
    question_count: int = Field(10, ge=1, le=20, description="题目数量")
    option_count: int = Field(4, ge=4, le=5, description="选项数量")
    include_explanation: bool = Field(True, description="是否包含解析")


class VocabularySkillsQuestion(BaseModel):
    """Word Palace Vocabulary Skills 题目"""
    question_id: int
    grade_level: str
    topic: str
    skill: str
    detail: str
    difficulty: str
    question_stem: str
    passage_or_sentence: Optional[str] = ""
    answer_choices: Dict[str, str]
    correct_answer: Union[str, List[str]]
    explanation: Optional[str] = ""
    tested_word: Optional[str] = ""
    common_error_tested: Optional[str] = ""


class VocabularySkillsGenerateResponse(BaseModel):
    """Word Palace Vocabulary Skills 生成响应"""
    test_title: str = "Vocabulary Skills Practice"
    grade_level: str
    topic: str
    skill: str
    difficulty: str
    question_count: int
    questions: List[VocabularySkillsQuestion]


class VocabularySkillsAnswerItem(BaseModel):
    """Word Palace Vocabulary Skills 单题作答"""
    question_id: int
    student_answer: Union[str, List[str]]


class VocabularySkillsEvaluateRequest(BaseModel):
    """Word Palace Vocabulary Skills 评估请求"""
    questions: List[VocabularySkillsQuestion]
    answers: List[VocabularySkillsAnswerItem]
    grade_level: Optional[str] = Field(None, description="本次练习年级")
    topic: Optional[str] = Field(None, description="本次练习 Topic")
    skill: Optional[str] = Field(None, description="本次练习 Skill")
    difficulty: Optional[VocabularySkillsDifficulty] = Field(None, description="本次练习难度")
    question_count: Optional[int] = Field(None, ge=1, le=20, description="本次练习题量")


class VocabularySkillsEvaluationResponse(BaseModel):
    """Word Palace Vocabulary Skills 评估响应"""
    module: str = "word_vocabulary_skills"
    module_label: str = "Vocabulary Skills"
    grade_level: str = ""
    topic: str = ""
    skill: str = ""
    difficulty: str = ""
    question_count: int = 0
    score: float = 0
    accuracy: str = "0%"
    total: int = 0
    total_count: int = 0
    correct_count: int = 0
    overall: Dict[str, Any] = Field(default_factory=dict)
    detail_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    question_results: List[Dict[str, Any]] = Field(default_factory=list)
    weak_knowledge_points: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_next_practice: List[Dict[str, Any]] = Field(default_factory=list)
    skill_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    student_summary: str = ""
    parent_teacher_summary: str = ""
