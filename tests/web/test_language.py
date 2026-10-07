"""UI language does not alter paper/figure data, dimensions or agent payloads."""
from pathlib import Path
import pytest
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_chinese_controls_and_english_artifacts():
    with open_lab(viewport=(2560,1440)) as lab:
        p=lab.page;p.click('#ui-language')
        p.wait_for_function("document.documentElement.lang==='zh-CN'")
        assert p.locator('#setup h1').inner_text()=='配置你的图表'
        p.click('[data-venue="neurips2026"]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        original=lab.export_bundle();svg=lab.wait_for_render()['svg']
        assert p.locator('#copy-handoff').inner_text()=='🤖 复制给 Agent'
        assert p.locator('#figure-assessment').inner_text()=='✅ 图表状态良好！'
        assert p.locator('[data-group=lines] summary').inner_text()=='线条与标记'
        good=p.locator('#figure-assessment').evaluate('(n)=>getComputedStyle(n).backgroundColor')
        lab.set_control('fonts.size_xtick_pt',4);lab.wait_for_render()
        assert p.locator('#warning-rail').is_visible()
        assert p.locator('#figure-assessment').inner_text()=='⚠️ 有 1 项警告。'
        assert p.locator('.warning-card').first.locator('strong').inner_text()=='⚠️ 文字过小'
        assert '小于 6 pt' in p.locator('.warning-card').first.inner_text()
        assert p.locator('#figure-assessment').evaluate('(n)=>getComputedStyle(n).backgroundColor')!=good
        p.get_by_role('button',name='调整设置').first.click()
        p.click('#undo-style');svg=lab.wait_for_render()['svg']
        p.click('#ui-language')
        p.wait_for_function("document.documentElement.lang==='en'")
        assert p.locator('#copy-handoff').inner_text()=='🤖 Copy for Agents'
        assert lab.wait_for_render()['svg']==svg
        assert lab.export_bundle()['spec']==original['spec']
        assert lab.export_bundle()['profile']==original['profile']
        p.click('#ui-language')
        folder=Path('.tmp/interface');folder.mkdir(exist_ok=True,parents=True)
        p.screenshot(path=str(folder/'chinese-2k.png'))
        p.reload();p.wait_for_selector('#setup-next')
        assert p.locator('#ui-language').get_attribute('data-language')=='zh'
        assert p.locator('#setup h1').inner_text()=='配置你的图表'
        assert not lab.page_errors


def test_chinese_phone_has_no_horizontal_overflow():
    with open_lab(viewport=(390,844)) as lab:
        p=lab.page;p.click('#ui-language');lab.wait_ready();lab.wait_for_render()
        assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
        p.select_option('#example','scatter');lab.wait_for_render()
        assert p.locator('#data-origin').inner_text()=='示例数据'
        assert not lab.page_errors
