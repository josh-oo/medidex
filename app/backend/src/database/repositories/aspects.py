from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
import re

from ..models import Study
from ..tagstorage import TAG_TABLES
from typing import List, Optional

class AspectRepository:
    def __init__(self, db : AsyncSession):
        self.db = db

    async def get_all_tags(self, category: str, ids: List[int]):
        """All tags of a category (a key of config/study.yaml), or only those with the given ids."""
        tag = TAG_TABLES[category].tag
        stmt = select(tag)
        if ids:
            stmt = stmt.where(tag.id.in_(ids))
        return (await self.db.execute(stmt)).scalars().all()

    async def get_all_countries(self, prefix: Optional[str]) -> List[str]:
        # Get all non-null Countries values
        stmt = select(Study.countries).where(Study.countries.isnot(None))
        rows = (await self.db.execute(stmt)).scalars().all()
        
        # Split by '//' and collect all unique countries
        countries_set = set()
        for countries_str in rows:
            if countries_str:
                # Split by '//' and strip whitespace from each country
                cleaned = re.sub(r'\{[^}]*\}|\[[^\]]*\]', '', countries_str).strip()
                country_list = [country.strip() for country in cleaned.replace("//", "/").split("/")]
                for country in country_list:
                    if country == "USA and":
                        print(countries_str)
                    countries_set.add(country)

        blacklist = ["NR", "USA and USA", "USA and", "SlovakiaUSA", "Slovania", "Morroco", "Japan and Japan", "Greece OR UK", "Chile and China", ""]
        
        # Remove blacklisted items
        for item in blacklist:
            countries_set.discard(item)
        
        # Convert to sorted list
        all_countries = sorted(countries_set)
        
        # Apply prefix filter if provided
        if prefix:
            prefix_lower = prefix.lower()
            all_countries = [c for c in all_countries if c.lower().startswith(prefix_lower)]
        
        return all_countries