"""Recipient-type categories as USASpending exposes them.

Individual award rows from ``spending_by_award`` do not carry a usable
recipient type (the business-type fields come back null for assistance
awards). What the API does support is filtering by ``recipient_type_names``,
so the type mix is built from one count query per category.

Note: the API returns 0, not an error, for an unknown category name, so the
names below were checked against live responses.
"""

from __future__ import annotations

# Displayed mix, in order. Each label maps to the API category queried.
MIX_CATEGORIES: list[tuple[str, str]] = [
    ("nonprofit", "nonprofit"),
    ("higher education", "higher_education"),
    ("state government", "regional_and_state_government"),
    ("local government", "local_government"),
    ("tribal government", "indian_native_american_tribal_government"),
    ("business", "category_business"),
    ("individuals", "individuals"),
]

# Parent category used to derive "other government" (federal, territorial,
# authorities and commissions, interstate) as government minus the three
# government subtypes above.
GOVERNMENT_PARENT = "government"
GOVERNMENT_SUBTYPES = [
    "regional_and_state_government",
    "local_government",
    "indian_native_american_tribal_government",
]

# Union used to count awards with no recipient type at all.
CLASSIFIED_UNION = [
    "nonprofit",
    "higher_education",
    "government",
    "category_business",
    "individuals",
]

# --org-type choice -> (display label, API category)
ORG_TYPES: dict[str, tuple[str, str]] = {
    "nonprofit": ("nonprofit", "nonprofit"),
    "university": ("higher education", "higher_education"),
    "state_gov": ("state government", "regional_and_state_government"),
    "local_gov": ("local government", "local_government"),
    "tribal": ("tribal government", "indian_native_american_tribal_government"),
    "for_profit": ("business", "category_business"),
    "small_business": ("small business", "small_business"),
}
