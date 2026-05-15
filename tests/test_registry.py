"""Tests for EntityRegistry."""

from feeflow.matching.registry import EntityRegistry, EntityRecord


class TestEntityRecord:
    def test_add_alias(self):
        record = EntityRecord(id="人民医院")
        record.add_alias("市人民医院")
        assert "市人民医院" in record.aliases

    def test_all_name_variants(self):
        record = EntityRecord(id="人民医院", aliases=["市人民医院", "县人民医院"])
        variants = record.all_name_variants()
        assert "人民医院" in variants
        assert "市人民医院" in variants
        assert "县人民医院" in variants


class TestEntityRegistry:
    def test_get_or_create(self):
        registry = EntityRegistry()
        entity = registry.get_or_create("人民医院")
        assert entity.id == "人民医院"
        assert registry.entity_count() == 1

    def test_get_or_create_duplicate(self):
        registry = EntityRegistry()
        e1 = registry.get_or_create("人民医院")
        e2 = registry.get_or_create("人民医院")
        assert e1 is e2  # Same entity
        assert registry.entity_count() == 1

    def test_resolve_by_name(self):
        registry = EntityRegistry()
        registry.get_or_create("人民医院")
        entity = registry.resolve("人民医院")
        assert entity is not None
        assert entity.id == "人民医院"

    def test_resolve_with_alias(self):
        registry = EntityRegistry()
        entity = registry.get_or_create("人民医院")
        entity.add_alias("市人民医院")
        # Alias should resolve after rebuild
        resolved, score = registry.resolve_with_score("市人民医院")
        assert resolved is not None
        assert resolved.id == "人民医院"

    def test_resolve_not_found(self):
        registry = EntityRegistry()
        entity = registry.resolve("不存在的医院")
        assert entity is None

    def test_summary(self):
        registry = EntityRegistry()
        registry.get_or_create("人民医院")
        summary = registry.summary()
        assert summary["total_entities"] == 1

    def test_search_by_tag(self):
        registry = EntityRegistry()
        entity = registry.get_or_create("人民医院")
        entity.tags.append("hospital")
        results = registry.search(tags=["hospital"])
        assert len(results) == 1
        results = registry.search(tags=["clinic"])
        assert len(results) == 0

    def test_merge(self):
        registry = EntityRegistry()
        e1 = registry.get_or_create("人民医院")
        e1.attributes["region"] = "成都"
        e2 = registry.get_or_create("市人民医院")
        e2.attributes["code"] = "5101"

        merged = registry.merge("市人民医院", "人民医院")
        assert merged.id == "人民医院"
        assert merged.attributes["region"] == "成都"
        assert merged.attributes["code"] == "5101"
        assert registry.resolve("市人民医院") is not None  # alias still works
