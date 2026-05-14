"""Integration smoke tests (require running DB)."""

import pytest


@pytest.mark.skip(reason="Requires running PostgreSQL")
class TestSystemInit:
    async def test_needs_init_returns_true_on_empty_db(self, db_session):
        from app.system.service import InitService
        svc = InitService(db_session)
        assert await svc.needs_init() is True

    async def test_initialize_creates_admin(self, db_session):
        from app.system.service import InitService
        svc = InitService(db_session)
        user = await svc.initialize("admin", "admin@test.com", "securepassword")
        assert user.username == "admin"
        assert user.role.value == "system_admin"

    async def test_double_init_raises(self, db_session):
        from app.system.service import InitService
        svc = InitService(db_session)
        await svc.initialize("admin", "admin@test.com", "securepassword")
        with pytest.raises(ValueError, match="already initialized"):
            await svc.initialize("admin2", "admin2@test.com", "securepassword")


@pytest.mark.skip(reason="Requires running PostgreSQL")
class TestNotificationService:
    async def test_send_and_list(self, db_session, admin_user):
        from app.system.service import NotificationService
        svc = NotificationService(db_session)
        notif = await svc.send(admin_user.id, "info", "Test notification")
        assert notif.is_read is False

        items, total = await svc.list_notifications(admin_user.id)
        assert len(items) == 1
        assert total == 1

    async def test_unread_count(self, db_session, admin_user):
        from app.system.service import NotificationService
        svc = NotificationService(db_session)
        await svc.send(admin_user.id, "info", "N1")
        await svc.send(admin_user.id, "info", "N2")
        assert await svc.unread_count(admin_user.id) == 2

    async def test_mark_all_read(self, db_session, admin_user):
        from app.system.service import NotificationService
        svc = NotificationService(db_session)
        await svc.send(admin_user.id, "info", "N1")
        await svc.send(admin_user.id, "info", "N2")
        await svc.mark_all_read(admin_user.id)
        assert await svc.unread_count(admin_user.id) == 0


@pytest.mark.skip(reason="Requires running PostgreSQL")
class TestQuotas:
    async def test_kb_quota_from_system_settings(self, db_session, admin_user):
        from app.knowledge.service import KBService
        svc = KBService(db_session)
        # Default quota should not block on first KB
        await svc.check_kb_quota(admin_user.id)
