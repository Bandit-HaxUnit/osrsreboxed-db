"""Regression: real singular shop pages are not skipped as generic type pages."""

from scripts.shops.shops_properties import is_generic_shop_page


def test_real_singular_shop_pages_are_kept():
    assert is_generic_shop_page("Candle Shop") is False
    assert is_generic_shop_page("Pie Shop") is False
    assert is_generic_shop_page("Forestry Shop") is False


def test_generic_plural_shop_pages_are_skipped():
    assert is_generic_shop_page("Axe shops") is True
    assert is_generic_shop_page("Magic shops") is True


def test_non_shop_and_placeholder_pages_are_skipped():
    assert is_generic_shop_page("General store") is True
    assert is_generic_shop_page("Shop") is True
    assert is_generic_shop_page("Category:Shops") is True
