"""
Skills 知识点文件服务
按 data/skills/index.json 管理多个 skills JSON 文件。
"""
import json
import os
import threading
from typing import Any, Dict, List, Optional

from config import config


class SkillsService:
    """读取和维护 Skills 知识点数据。"""

    def __init__(self):
        self.skills_dir = os.path.join(config.DATA_DIR, "skills")
        self.index_path = os.path.join(self.skills_dir, "index.json")
        self._lock = threading.RLock()

    def list_sections(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._read_index_unlocked().get("files", [])

    def list_skills(
        self,
        module: Optional[str] = None,
        section: Optional[str] = None,
        grade: Optional[str] = None,
        topic: Optional[str] = None,
        skill: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        with self._lock:
            rows: List[Dict[str, Any]] = []
            for source in self._matching_sources_unlocked(module, section):
                data = self._read_skill_file_unlocked(source["file"])
                for item in data.get("skills", []):
                    row = {
                        "module": item.get("module") or data.get("module") or source.get("module"),
                        "section": item.get("section") or data.get("section") or source.get("section"),
                        **item
                    }
                    if grade and row.get("grade") != grade:
                        continue
                    if topic and row.get("topic") != topic:
                        continue
                    if skill and row.get("skill") != skill:
                        continue
                    if enabled_only and not bool(row.get("enabled", True)):
                        continue
                    rows.append(row)
            rows.sort(key=lambda x: (x.get("grade", ""), x.get("topic", ""), x.get("skill", ""), x.get("sort_order", 0)))
            return rows

    def get_tree(self, module: Optional[str] = None, section: Optional[str] = None, enabled_only: bool = True) -> Dict[str, Any]:
        skills = self.list_skills(module=module, section=section, enabled_only=enabled_only)
        tree: Dict[str, Any] = {"grades": []}
        grade_map: Dict[str, Any] = {}

        for row in skills:
            grade = row.get("grade", "")
            topic = row.get("topic", "")
            skill_name = row.get("skill", "")
            if not grade or not topic or not skill_name:
                continue

            grade_node = grade_map.setdefault(grade, {"grade": grade, "topics": [], "total": 0})
            topic_map = grade_node.setdefault("_topic_map", {})
            topic_node = topic_map.setdefault(topic, {"topic": topic, "skills": [], "total": 0})
            skill_map = topic_node.setdefault("_skill_map", {})
            skill_node = skill_map.setdefault(skill_name, {
                "skill": skill_name,
                "details": [],
                "total": 0,
                "enabled_count": 0
            })

            detail = {
                "id": row.get("id"),
                "detail": row.get("detail", ""),
                "enabled": bool(row.get("enabled", True)),
                "difficulty": row.get("difficulty", ""),
                "question_types": row.get("question_types", []),
                "tags": row.get("tags", [])
            }
            skill_node["details"].append(detail)
            skill_node["total"] += 1
            skill_node["enabled_count"] += 1 if detail["enabled"] else 0
            topic_node["total"] += 1
            grade_node["total"] += 1

        for grade_node in grade_map.values():
            topics = []
            for topic_node in grade_node.pop("_topic_map", {}).values():
                skills_list = []
                for skill_node in topic_node.pop("_skill_map", {}).values():
                    skill_node["details"].sort(key=lambda x: x.get("detail", ""))
                    skills_list.append(skill_node)
                topic_node["skills"] = sorted(skills_list, key=lambda x: x.get("skill", ""))
                topics.append(topic_node)
            grade_node["topics"] = sorted(topics, key=lambda x: x.get("topic", ""))
            tree["grades"].append(grade_node)

        tree["grades"].sort(key=lambda x: x.get("grade", ""))
        tree["total"] = len(skills)
        return tree

    def update_skill(self, skill_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"detail", "difficulty", "question_types", "tags", "enabled", "sort_order"}
        clean_updates = {k: v for k, v in updates.items() if k in allowed}
        if not clean_updates:
            raise ValueError("没有可更新的字段")

        with self._lock:
            for source in self._read_index_unlocked().get("files", []):
                data = self._read_skill_file_unlocked(source["file"])
                for item in data.get("skills", []):
                    if item.get("id") == skill_id:
                        item.update(clean_updates)
                        self._write_skill_file_unlocked(source["file"], data)
                        return {
                            "module": item.get("module") or data.get("module") or source.get("module"),
                            "section": item.get("section") or data.get("section") or source.get("section"),
                            **item
                        }
        raise ValueError(f"Skill 不存在: {skill_id}")

    def _matching_sources_unlocked(self, module: Optional[str], section: Optional[str]) -> List[Dict[str, Any]]:
        sources = []
        for source in self._read_index_unlocked().get("files", []):
            if module and source.get("module") != module:
                continue
            if section and source.get("section") != section:
                continue
            if not bool(source.get("enabled", True)):
                continue
            sources.append(source)
        return sources

    def _read_index_unlocked(self) -> Dict[str, Any]:
        return self._read_json_unlocked(self.index_path, {"version": 1, "files": []})

    def _read_skill_file_unlocked(self, file_name: str) -> Dict[str, Any]:
        return self._read_json_unlocked(os.path.join(self.skills_dir, file_name), {"version": 1, "skills": []})

    def _write_skill_file_unlocked(self, file_name: str, data: Dict[str, Any]) -> None:
        path = os.path.join(self.skills_dir, file_name)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)

    def _read_json_unlocked(self, path: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not os.path.exists(path):
            return fallback.copy()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else fallback.copy()


_skills_service: Optional[SkillsService] = None


def get_skills_service() -> SkillsService:
    global _skills_service
    if _skills_service is None:
        _skills_service = SkillsService()
    return _skills_service
