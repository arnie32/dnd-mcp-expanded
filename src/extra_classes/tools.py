"""MCP tools for extra D&D classes sourced from BG3 mods."""

import json
import sqlite3


def register_extra_classes_tools(app, db: sqlite3.Connection) -> None:
    """Register all extra-classes tools on the FastMCP app."""

    @app.tool()
    def list_extra_classes() -> list[dict]:
        """List all extra D&D classes from BG3 mods with name, role, and tags."""
        rows = db.execute(
            "SELECT class_name, role, tags, ruleset, is_official, source"
            " FROM classes ORDER BY class_name"
        ).fetchall()
        return [
            {
                "name": r["class_name"],
                "role": r["role"],
                "tags": json.loads(r["tags"] or "[]"),
                "ruleset": r["ruleset"],
                "is_official": bool(r["is_official"]),
                "source": r["source"],
            }
            for r in rows
        ]

    @app.tool()
    def get_extra_class(
        class_name: str,
        level: int | None = None,
        subclass_name: str | None = None,
    ) -> dict:
        """Get detailed class progression for an extra D&D class from BG3 mods.

        Optionally filter by level (1-20) and/or subclass name.
        Returns class metadata, features_by_level, and abilities_by_level with
        mechanical stats (damage type, range, shape, use costs, etc.).
        """
        row = db.execute(
            "SELECT * FROM classes WHERE lower(class_name) = lower(?)", (class_name,)
        ).fetchone()
        if not row:
            return {"error": f"Class '{class_name}' not found. Use list_extra_classes() to see available classes."}

        result = {
            "class_name": row["class_name"],
            "role": row["role"],
            "tags": json.loads(row["tags"] or "[]"),
            "ruleset": row["ruleset"],
            "is_official": bool(row["is_official"]),
            "source": row["source"],
            "source_mods": json.loads(row["source_mods"] or "[]"),
            "subclasses": json.loads(row["subclasses"] or "[]"),
            "subclass_gain_level": row["subclass_gain_level"],
            "skill_options": json.loads(row["skill_options"] or "[]"),
            "primary_stats": json.loads(row["primary_stats"] or "[]"),
            "proficiencies": json.loads(row["proficiencies"] or "{}"),
        }

        # Feature strings (from dnd_classes_expanded_with_levels.json)
        feat_q = (
            "SELECT level, subclass_name, features FROM class_features"
            " WHERE lower(class_name) = lower(?)"
        )
        feat_params: list = [class_name]
        if level is not None:
            feat_q += " AND level = ?"
            feat_params.append(level)
        if subclass_name is not None:
            feat_q += " AND (subclass_name IS NULL OR lower(subclass_name) = lower(?))"
            feat_params.append(subclass_name)
        feat_q += " ORDER BY level, subclass_name"

        features_by_level: dict[str, dict] = {}
        for fr in db.execute(feat_q, feat_params).fetchall():
            lv = str(fr["level"])
            if lv not in features_by_level:
                features_by_level[lv] = {"class": [], "subclasses": {}}
            if fr["subclass_name"] is None:
                features_by_level[lv]["class"] = json.loads(fr["features"] or "[]")
            else:
                features_by_level[lv]["subclasses"][fr["subclass_name"]] = json.loads(
                    fr["features"] or "[]"
                )
        result["features_by_level"] = features_by_level

        # Ability refs joined with mechanical details
        ab_q = """
            SELECT ar.level, ar.subclass_name, ar.raw_id, ar.feature_type, ar.confidence,
                   a.name, a.description, a.type, a.damage_type, a.use_costs,
                   a.range, a.shape, a.angle, a.maximum_targets, a.spell_school,
                   a.area_radius, a.target_conditions, a.boosts
            FROM class_ability_refs ar
            LEFT JOIN abilities a ON ar.raw_id = a.raw_id
            WHERE lower(ar.class_name) = lower(?)
        """
        ab_params: list = [class_name]
        if level is not None:
            ab_q += " AND ar.level = ?"
            ab_params.append(level)
        if subclass_name is not None:
            ab_q += " AND (ar.subclass_name IS NULL OR lower(ar.subclass_name) = lower(?))"
            ab_params.append(subclass_name)
        ab_q += " ORDER BY ar.level, ar.subclass_name, ar.raw_id"

        abilities_by_level: dict[str, list] = {}
        for ar in db.execute(ab_q, ab_params).fetchall():
            lv = str(ar["level"])
            if lv not in abilities_by_level:
                abilities_by_level[lv] = []
            abilities_by_level[lv].append(
                {k: ar[k] for k in ar.keys()}
            )
        result["abilities_by_level"] = abilities_by_level

        return result

    @app.tool()
    def get_extra_abilities(raw_ids: list[str]) -> list[dict]:
        """Get full ability details for up to 20 raw_ids from BG3 mod abilities.

        Includes all mechanical fields: damage type, range, shape, angle,
        maximum targets, target conditions, use costs, boosts, spell roll, etc.
        """
        if not raw_ids:
            return []
        raw_ids = raw_ids[:20]
        placeholders = ",".join("?" * len(raw_ids))
        rows = db.execute(
            f"SELECT * FROM abilities WHERE raw_id IN ({placeholders})", raw_ids
        ).fetchall()
        return [dict(r) for r in rows]

    @app.tool()
    def search_extra_abilities(query: str, class_name: str | None = None) -> list[dict]:
        """Search BG3 mod abilities by name or description text using full-text search.

        Optionally restrict results to abilities belonging to a specific class.
        Returns up to 10 results ordered by relevance, with key mechanical fields.
        """
        fts_q = "SELECT raw_id FROM abilities_fts WHERE abilities_fts MATCH ? ORDER BY rank LIMIT 50"
        matched_ids = [r["raw_id"] for r in db.execute(fts_q, (query,)).fetchall()]
        if not matched_ids:
            return []

        if class_name:
            # Filter to ids that appear in the given class
            class_ids = {
                r["raw_id"]
                for r in db.execute(
                    "SELECT DISTINCT raw_id FROM class_ability_refs WHERE lower(class_name) = lower(?)",
                    (class_name,),
                ).fetchall()
            }
            matched_ids = [i for i in matched_ids if i in class_ids]

        matched_ids = matched_ids[:10]
        if not matched_ids:
            return []

        placeholders = ",".join("?" * len(matched_ids))
        rows = db.execute(
            f"SELECT raw_id, name, description, type, damage_type, use_costs,"
            f" range, shape, angle, maximum_targets, spell_school, area_radius"
            f" FROM abilities WHERE raw_id IN ({placeholders})",
            matched_ids,
        ).fetchall()
        # Re-order by the FTS rank order
        order = {rid: i for i, rid in enumerate(matched_ids)}
        return sorted([dict(r) for r in rows], key=lambda r: order.get(r["raw_id"], 999))
