"""
词库管理模块
负责词库文件的加载、缓存和词汇随机抽取
"""
import os
import random
import logging
from typing import List, Dict, Optional
from config import config

logger = logging.getLogger(__name__)


class VocabularyManager:
    """词库管理器类"""
    
    def __init__(self):
        """初始化词库管理器"""
        self.data_dir = config.DATA_DIR
        self._cache: Dict[str, List[str]] = {}
        logger.info(f"VocabularyManager initialized with data_dir: {self.data_dir}")
    
    def load_library(self, library_name: str) -> List[str]:
        """
        加载指定词库文件
        
        Args:
            library_name: 词库名称(不含扩展名)
        
        Returns:
            词汇列表
        """
        # 检查缓存
        if library_name in self._cache:
            logger.debug(f"Library '{library_name}' loaded from cache")
            return self._cache[library_name]
        
        # 构建文件路径
        file_path = os.path.join(self.data_dir, f"{library_name}.txt")
        
        if not os.path.exists(file_path):
            logger.warning(f"Library file not found: {file_path}")
            return []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().replace("，", ",")  # 兼容中文逗号
                words = [w.strip() for w in content.split(",") if w.strip()]
            
            # 缓存词库
            self._cache[library_name] = words
            logger.info(f"Successfully loaded library '{library_name}' with {len(words)} words")
            return words
        
        except Exception as e:
            logger.error(f"Error loading library '{library_name}': {str(e)}")
            return []
    
    def get_random_words(self, library_name: str, count: int) -> List[str]:
        """
        从词库中随机抽取指定数量的词汇
        
        Args:
            library_name: 词库名称
            count: 抽取数量
        
        Returns:
            随机词汇列表
        """
        all_words = self.load_library(library_name)
        
        if not all_words:
            logger.warning(f"No words available in library '{library_name}'")
            return []
        
        # 确保抽取数量不超过词库大小
        safe_count = min(count, len(all_words))
        selected_words = random.sample(all_words, safe_count)
        
        logger.info(f"Selected {safe_count} random words from '{library_name}'")
        return selected_words
    
    def get_all_libraries(self) -> List[str]:
        """
        获取所有可用的词库名称
        
        Returns:
            词库名称列表(不含扩展名)
        """
        if not os.path.exists(self.data_dir):
            logger.warning(f"Data directory not found: {self.data_dir}")
            return []
        
        libraries = []
        for filename in os.listdir(self.data_dir):
            if filename.endswith(".txt"):
                library_name = filename[:-4]  # 移除 .txt 扩展名
                libraries.append(library_name)
        
        logger.info(f"Found {len(libraries)} libraries: {libraries}")
        return libraries
    
    def clear_cache(self, library_name: Optional[str] = None):
        """
        清除词库缓存
        
        Args:
            library_name: 指定词库名称，若为 None 则清除所有缓存
        """
        if library_name:
            if library_name in self._cache:
                del self._cache[library_name]
                logger.info(f"Cleared cache for library '{library_name}'")
        else:
            self._cache.clear()
            logger.info("Cleared all library caches")
    
    def get_library_info(self, library_name: str) -> Dict[str, any]:
        """
        获取词库信息
        
        Args:
            library_name: 词库名称
        
        Returns:
            词库信息字典
        """
        words = self.load_library(library_name)
        
        return {
            "name": library_name,
            "total_words": len(words),
            "is_cached": library_name in self._cache,
            "file_path": os.path.join(self.data_dir, f"{library_name}.txt")
        }


# 全局词库管理器实例(单例模式)
_vocabulary_manager_instance: Optional[VocabularyManager] = None


def get_vocabulary_manager() -> VocabularyManager:
    """
    获取词库管理器实例(单例)
    
    Returns:
        VocabularyManager 实例
    """
    global _vocabulary_manager_instance
    if _vocabulary_manager_instance is None:
        _vocabulary_manager_instance = VocabularyManager()
    return _vocabulary_manager_instance
