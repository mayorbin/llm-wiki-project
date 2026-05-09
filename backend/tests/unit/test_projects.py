# backend/tests/unit/test_projects.py
"""项目服务测试。"""
import pytest
from app.config import reset_settings
from app.storage.database import init_db, close_all_db
from app.services.auth_service import register_user
from app.services import project_service as svc


@pytest.fixture(autouse=True)
def setup_teardown(monkeypatch, tmp_path):
    """每个测试使用独立的临时数据和密钥。"""
    monkeypatch.setenv("LLM_WIKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_WIKI_SECRET_KEY", "test-secret-key-must-be-32-chars!!")
    monkeypatch.setenv("LLM_WIKI_LLM_API_KEY", "sk-test-dummy")
    reset_settings()
    close_all_db()
    init_db(str(tmp_path))
    yield
    close_all_db()


def _create_user_and_project(username="bob", project_name="测试项目"):
    """辅助函数：创建用户和项目，返回 (user, project)。"""
    user = register_user(username, "password123", username)
    project = svc.create_project(project_name, "项目描述", user.id)
    return user, project


class TestCreateProject:
    """创建项目测试。"""

    def test_创建项目成功(self):
        """创建项目后返回正确的字段。"""
        user = register_user("alice", "pw123", "Alice")
        result = svc.create_project("我的知识库", "LLM Wiki", user.id)

        assert result["name"] == "我的知识库"
        assert result["description"] == "LLM Wiki"
        assert result["status"] == "active"
        assert result["user_role"] == "owner"
        assert result["id"].startswith("p_")

    def test_空名称创建失败(self):
        """空名称或纯空格必须拒绝。"""
        user = register_user("eve", "pw123")
        with pytest.raises(ValueError, match="项目名称"):
            svc.create_project("", "desc", user.id)
        with pytest.raises(ValueError, match="项目名称"):
            svc.create_project("   ", "desc", user.id)

    def test_创建者自动成为owner(self):
        """创建项目后，创建者应自动加入并成为 owner。"""
        user = register_user("dave", "pw123")
        project = svc.create_project("Test", "", user.id)
        members = svc.list_members(project["id"], user.id)
        assert len(members) == 1
        assert members[0]["user_id"] == user.id
        assert members[0]["role"] == "owner"


class TestListProjects:
    """项目列表测试。"""

    def test_列出用户项目(self):
        """用户应能看到自己参与的项目。"""
        user, project = _create_user_and_project("frank", "Frank的知识库")
        result = svc.list_projects(user.id)
        assert len(result) == 1
        assert result[0]["id"] == project["id"]

    def test_无项目用户返回空列表(self):
        """没有项目的用户应返回空列表。"""
        user = register_user("ghost", "pw123")
        assert svc.list_projects(user.id) == []

    def test_其他用户看不到不属于自己的项目(self):
        """用户不应看到自己未加入的项目。"""
        u1 = register_user("u1", "pw123")
        u2 = register_user("u2", "pw123")
        svc.create_project("U1的知识库", "", u1.id)
        # u2 看不到 u1 的项目
        assert svc.list_projects(u2.id) == []


class TestUpdateProject:
    """更新项目测试。"""

    def test_owner可更新项目(self):
        """owner 可以更新项目名称和描述。"""
        user, project = _create_user_and_project("george", "旧名称")
        updated = svc.update_project(project["id"], user.id, name="新名称")
        assert updated["name"] == "新名称"

    def test_非owner更新失败(self):
        """非 owner 不能更新项目信息。"""
        owner = register_user("owner1", "pw123")
        editor = register_user("editor1", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, editor.id, "editor")

        with pytest.raises(PermissionError, match="仅有项目 owner"):
            svc.update_project(project["id"], editor.id, name="Hacked")


class TestProjectPermissions:
    """权限控制测试。"""

    def test_viewer不能添加成员(self):
        """viewer 无权添加成员。"""
        owner = register_user("owner2", "pw123")
        viewer = register_user("viewer2", "pw123")
        target = register_user("target2", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, viewer.id, "viewer")

        with pytest.raises(PermissionError):
            svc.add_member(project["id"], viewer.id, target.id, "editor")

    def test_不能直接移除owner(self):
        """不能通过 remove_member 直接移除 owner。"""
        owner = register_user("owner3", "pw123")
        member = register_user("member3", "pw123")
        target = register_user("target3", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, member.id, "editor")
        svc.add_member(project["id"], owner.id, target.id, "viewer")

        # 让另一个 editor 尝试移除 owner——应失败
        with pytest.raises(PermissionError):
            svc.remove_member(project["id"], member.id, target.id)

    def test_viewer可读设置(self):
        """viewer 可以读取项目设置。"""
        owner = register_user("owner4", "pw123")
        viewer = register_user("viewer4", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, viewer.id, "viewer")

        settings = svc.get_project_settings(project["id"], viewer.id)
        assert "settings" in settings


class TestMemberManagement:
    """成员管理测试。"""

    def test_添加成员成功(self):
        """owner 可以添加新成员。"""
        owner = register_user("owner5", "pw123")
        member = register_user("member5", "pw123")
        project = svc.create_project("Proj", "", owner.id)

        result = svc.add_member(project["id"], owner.id, member.id, "editor")
        assert result["role"] == "editor"
        assert result["user_id"] == member.id

        members = svc.list_members(project["id"], owner.id)
        assert len(members) == 2

    def test_重复添加失败(self):
        """不能重复添加同一成员。"""
        owner = register_user("owner6", "pw123")
        member = register_user("member6", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, member.id, "editor")

        with pytest.raises(ValueError, match="已是项目成员"):
            svc.add_member(project["id"], owner.id, member.id, "editor")

    def test_移除成员成功(self):
        """owner 可以移除成员。"""
        owner = register_user("owner7", "pw123")
        member = register_user("member7", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, member.id, "editor")

        svc.remove_member(project["id"], owner.id, member.id)
        members = svc.list_members(project["id"], owner.id)
        assert len(members) == 1


class TestTransferOwnership:
    """所有权转让测试。"""

    def test_转让成功(self):
        """owner 可以将所有权转让给其他成员。"""
        owner = register_user("owner8", "pw123")
        member = register_user("member8", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, member.id, "editor")

        result = svc.transfer_ownership(project["id"], owner.id, member.id)
        assert result["new_owner"] == member.id

        # 验证新 owner 权限
        updated = svc.update_project(project["id"], member.id, name="新名字")
        assert updated["name"] == "新名字"

    def test_非成员不可接收所有权(self):
        """不能将所有权转让给非项目成员。"""
        owner = register_user("owner9", "pw123")
        outsider = register_user("outsider9", "pw123")
        project = svc.create_project("Proj", "", owner.id)

        with pytest.raises(ValueError, match="不是项目成员"):
            svc.transfer_ownership(project["id"], owner.id, outsider.id)


class TestDeleteProject:
    """删除项目测试。"""

    def test_owner可删除项目(self):
        """owner 可以删除项目。"""
        user, project = _create_user_and_project("zack", "Zack的项目")
        svc.delete_project(project["id"], user.id)
        # 删除后无法再查看
        with pytest.raises(ValueError, match="不存在"):
            svc.get_project(project["id"], user.id)

    def test_非owner删除失败(self):
        """非 owner 不能删除项目。"""
        owner = register_user("owner10", "pw123")
        editor = register_user("editor10", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, editor.id, "editor")

        with pytest.raises(PermissionError, match="仅有项目 owner"):
            svc.delete_project(project["id"], editor.id)


class TestProjectSettings:
    """项目设置测试。"""

    def test_获取默认设置(self):
        """新项目的设置应为空 dict。"""
        user, project = _create_user_and_project("settings1", "设置测试")
        result = svc.get_project_settings(project["id"], user.id)
        assert result["settings"] == {}

    def test_更新并获取设置(self):
        """更新设置后应能正确读取。"""
        user, project = _create_user_and_project("settings2", "设置测试")
        svc.update_project_settings(
            project["id"], user.id,
            {"llm_model": "deepseek-v4", "chunk_size": 2000},
        )
        result = svc.get_project_settings(project["id"], user.id)
        assert result["settings"]["llm_model"] == "deepseek-v4"
        assert result["settings"]["chunk_size"] == 2000

    def test_viewer不可修改设置(self):
        """viewer 不能修改项目设置。"""
        owner = register_user("owner11", "pw123")
        viewer = register_user("viewer11", "pw123")
        project = svc.create_project("Proj", "", owner.id)
        svc.add_member(project["id"], owner.id, viewer.id, "viewer")

        with pytest.raises(PermissionError):
            svc.update_project_settings(project["id"], viewer.id, {"test": 1})
