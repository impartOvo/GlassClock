"""Colour palettes for the desktop clock."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Skin:
    name: str
    base: str
    shade: str
    glow: str
    glow2: str
    ink: str
    ring: str
    effect: str = "glass"


SKINS = (
    Skin("流金琥珀", "#302319", "#100e13", "#ffbd57", "#a9631d", "#fff1da", "#ffd18b", "gold"),
    Skin("极光华彩", "#253047", "#16162f", "#b777ef", "#53c9d0", "#f9f6ff", "#f5edff", "aurora"),
    Skin("海蓝波光", "#10343e", "#081b28", "#42d5d4", "#68a3e7", "#f1ffff", "#8af5ed", "water"),
    Skin("午夜纯黑", "#20232b", "#101116", "#8c97a8", "#4f596a", "#f6f5f1", "#f0f2f4"),
    Skin("冰川纯蓝", "#36557a", "#1e385a", "#8cddff", "#6b9bd9", "#ffffff", "#bcf0ff"),
    Skin("珍珠纯白", "#d4d7d8", "#abb6c2", "#ffffff", "#d3dcf2", "#252d3a", "#677381", "light"),
    Skin("玫瑰香槟", "#b88286", "#7d5764", "#f5c5a7", "#d6a9bc", "#351c31", "#ffdac3", "light"),
    Skin("紫晶星辉", "#40264f", "#201528", "#bc83ee", "#8160cd", "#f8edff", "#e5c7ff", "stars"),
    Skin("翡翠水磨", "#204d3e", "#102b27", "#a4df9a", "#70c2a2", "#f1fff2", "#cdf6be"),
    Skin("银灰水晶", "#3d4653", "#202631", "#c5d7e3", "#8194a8", "#ffffff", "#f1f6f8"),
)
