"""
File: __init__.py
Description: Staff lifecycle Domain 的公開型別入口。
"""

from .retirement import StaffLifecycleState, StaffLifecycleTransition

__all__ = ["StaffLifecycleState", "StaffLifecycleTransition"]
