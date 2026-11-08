#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anteprojeto "Sobrado 4x20" - gerador dos desenhos.

Um único modelo geométrico (em metros) alimenta todos os produtos:
plantas, corte, fachada, quadro de áreas, SVG, DXF, HTML e PDF.
Para alterar o projeto, mude as coordenadas aqui e rode de novo:

    pip install shapely ezdxf
    python3 gerar_projeto.py

Convenções do modelo (plantas):
    x = largura do lote (0 = divisa esquerda de quem olha da rua, 4 = direita)
    y = profundidade   (0 = alinhamento da rua, 20 = fundo do lote)
Corte e fachada usam (u, z): u horizontal no desenho, z = altura.
"""
import html
import math
import os
import subprocess
import sys

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

RAIZ = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(RAIZ, "projeto")

# --------------------------------------------------------------------------
# Parâmetros gerais
# --------------------------------------------------------------------------
LOTE_W, LOTE_L = 4.00, 20.00
E = 0.15                  # paredes de divisa / externas
GARAGEM_L = 5.50          # comprimento da garagem (exigência do programa)
FIM_CASA = 14.70          # fundo da edificação
MURO_FUNDO = 19.85

# Escada reta encostada na divisa esquerda
N_ESPELHOS = 16
ESPELHO = 0.18
PISO_DEG = 0.28
ESC_X0, ESC_X1 = 0.15, 1.05
ESC_Y0 = 5.65
ESC_Y1 = round(ESC_Y0 + (N_ESPELHOS - 1) * PISO_DEG, 2)   # 9,85
VAZIO_Y0 = 6.45           # início do vazio sobre a escada (altura livre >= 2,10)

# Níveis
Z_CALCADA = 0.00
Z_GARAGEM = 0.05
Z_TERREO = 0.15
Z_SUP = round(Z_TERREO + N_ESPELHOS * ESPELHO, 2)          # 3,03
PE_DIREITO = 2.70
Z_LAJE_INF = round(Z_SUP - 0.18, 2)                        # 2,85 (fundo da laje)
Z_FORRO = round(Z_SUP + PE_DIREITO, 2)                     # 5,73
Z_LAJE_COB = round(Z_FORRO + 0.12, 2)                      # 5,85
Z_TELHA = 6.20
Z_PLATIBANDA = 6.60
Z_VIGA_FRENTE = 2.55      # fundo da viga sobre o portão

CORTE_X = 0.60            # posição do corte AA (passa pela escada)


def fmt(v, nd=2):
    return f"{v:.{nd}f}".replace(".", ",")


# --------------------------------------------------------------------------
# Estrutura de desenho
# --------------------------------------------------------------------------
class Drawing:
    """Lista de primitivas em coordenadas do mundo (metros).

    camadas (ordem de pintura): 0 pisos/áreas, 1 mobiliário, 2 paredes,
    3 esquadrias/símbolos, 4 cotas, 5 textos
    """

    def __init__(self, nome, plano=True):
        self.nome = nome
        self.plano = plano
        self.items = []
        self.walls, self.muros, self.cuts = [], [], []
        # vetor "para baixo na tela" e vetor do traço de cota, no mundo
        self.down = (1.0, 0.0) if plano else (0.0, -1.0)
        self.slash = (-1.0, 1.0) if plano else (1.0, 1.0)

    def add(self, layer, kind, cls, **kw):
        self.items.append(dict(layer=layer, kind=kind, cls=cls, **kw))

    def line(self, pts, cls="thin", layer=3):
        self.add(layer, "line", cls, pts=[tuple(p) for p in pts])

    def poly(self, pts, cls="furn", layer=1):
        self.add(layer, "poly", cls, pts=[tuple(p) for p in pts])

    def rect(self, x0, y0, x1, y1, cls="furn", layer=1):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], cls, layer)

    def circle(self, c, r, cls="furn", layer=1):
        self.add(layer, "circle", cls, c=tuple(c), r=r)

    def arc(self, c, r, a0, a1, cls="swing", layer=3):
        self.add(layer, "arc", cls, c=tuple(c), r=r, a0=a0, a1=a1)

    def area(self, geom, cls, layer=0):
        self.add(layer, "area", cls, geom=geom)

    def text(self, p, s, size=0.20, cls="label", anchor="middle", rot=0, layer=5):
        self.add(layer, "text", cls, p=tuple(p), s=s, size=size, anchor=anchor, rot=rot)

    def wall(self, x0, y0, x1, y1):
        self.walls.append(box(x0, y0, x1, y1))

    def muro(self, x0, y0, x1, y1):
        self.muros.append(box(x0, y0, x1, y1))

    def cut(self, x0, y0, x1, y1):
        self.cuts.append(box(x0, y0, x1, y1))

    def finalize(self, wall_cls="wall"):
        holes = unary_union(self.cuts) if self.cuts else None
        if self.walls:
            g = unary_union(self.walls)
            if holes is not None:
                g = g.difference(holes)
            self.area(g, wall_cls, layer=2)
        if self.muros:
            g = unary_union(self.muros)
            if holes is not None:
                g = g.difference(holes)
            self.area(g, "muro", layer=2)

    # rótulo de ambiente: nome + linhas secundárias, empilhados "para baixo na tela"
    def label(self, p, nome, *linhas, size=0.24, sub=0.18):
        dx, dy = self.down
        n = 1 + len(linhas)
        alturas = [size * 1.25] + [sub * 1.3] * len(linhas)
        total = sum(alturas)
        off = -total / 2 + alturas[0] / 2
        self.text((p[0] + dx * off, p[1] + dy * off), nome, size=size, cls="label")
        acc = off + alturas[0] / 2
        for i, ln in enumerate(linhas):
            acc += alturas[i + 1] / 2
            self.text((p[0] + dx * acc, p[1] + dy * acc), ln, size=sub, cls="sublabel")
            acc += alturas[i + 1] / 2
        return n


def ellipse_pts(cx, cy, rx, ry, n=28):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rounded_rect(x0, y0, x1, y1, r, n=6):
    pts = []
    for cx, cy, a in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            t = math.radians(a + 90 * i / n)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


# --------------------------------------------------------------------------
# Esquadrias e cotas
# --------------------------------------------------------------------------
def door(d, hinge, closed_tip, open_tip):
    d.line([hinge, open_tip], "door")
    a0 = math.atan2(closed_tip[1] - hinge[1], closed_tip[0] - hinge[0])
    a1 = math.atan2(open_tip[1] - hinge[1], open_tip[0] - hinge[0])
    d.arc(hinge, math.dist(hinge, open_tip), a0, a1)


def door_h(d, x0, x1, ya, yb, hinge_at, side):
    """Porta de giro em parede paralela ao eixo x (espessura ya..yb)."""
    d.cut(x0, ya, x1, yb)
    face = yb if side > 0 else ya
    hx, ox = (x0, x1) if hinge_at == "x0" else (x1, x0)
    door(d, (hx, face), (ox, face), (hx, face + side * (x1 - x0)))


def door_v(d, y0, y1, xa, xb, hinge_at, side):
    """Porta de giro em parede paralela ao eixo y (espessura xa..xb)."""
    d.cut(xa, y0, xb, y1)
    face = xb if side > 0 else xa
    hy, oy = (y0, y1) if hinge_at == "y0" else (y1, y0)
    door(d, (face, hy), (face, oy), (face + side * (y1 - y0), hy))


def window_h(d, x0, x1, ya, yb):
    d.cut(x0, ya, x1, yb)
    for y in (ya, yb):
        d.line([(x0, y), (x1, y)], "win")
    ym = (ya + yb) / 2
    for o in (-0.018, 0.018):
        d.line([(x0, ym + o), (x1, ym + o)], "glass")


def sliding_h(d, x0, x1, ya, yb):
    d.cut(x0, ya, x1, yb)
    t = yb - ya
    xm = (x0 + x1) / 2
    y1, y2 = ya + t * 0.33, ya + t * 0.67
    d.rect(x0, y1 - 0.022, xm + 0.06, y1 + 0.022, "leaf", layer=3)
    d.rect(xm - 0.06, y2 - 0.022, x1, y2 + 0.022, "leaf", layer=3)


def dim_chain(d, axis, pos, vals, ext=None, label_min=0.40, toff=None, size=0.17, labels=None):
    """Cadeia de cotas.

    axis=1: varia na 2ª coordenada, com a 1ª fixa em `pos`.
    axis=0: varia na 1ª coordenada, com a 2ª fixa em `pos`.
    ext: coordenada da borda do objeto para as linhas de chamada.
    """
    def P(v, w):  # (ao longo, perpendicular) -> mundo
        return (w, v) if axis == 1 else (v, w)

    # texto vertical na tela?
    vertical = (d.plano and axis == 0) or (not d.plano and axis == 1)
    if toff is None:
        toff = -0.12 if (d.plano or vertical) else 0.12
    rot = -90 if vertical else 0
    t = 0.07
    sx, sy = d.slash
    d.line([P(vals[0], pos), P(vals[-1], pos)], "dim", layer=4)
    for v in vals:
        a, b = P(v, pos)
        d.line([(a - sx * t, b - sy * t), (a + sx * t, b + sy * t)], "dimtick", layer=4)
        if ext is not None:
            sgn = 1 if pos > ext else -1
            d.line([P(v, ext + sgn * 0.06), P(v, pos + sgn * 0.08)], "dimext", layer=4)
    for i in range(len(vals) - 1):
        L = vals[i + 1] - vals[i]
        if L < label_min:
            continue
        lab = labels[i] if labels else fmt(L)
        d.text(P((vals[i] + vals[i + 1]) / 2, pos + toff), lab, size=size, cls="dimtext", rot=rot, layer=4)


# --------------------------------------------------------------------------
# Mobiliário (só referência de escala)
# --------------------------------------------------------------------------
def bed_head_x1(d, x0, y0, x1, y1):
    d.rect(x0, y0, x1, y1)
    w = y1 - y0
    d.rect(x1 - 0.48, y0 + 0.10, x1 - 0.12, y0 + w / 2 - 0.05)
    d.rect(x1 - 0.48, y0 + w / 2 + 0.05, x1 - 0.12, y1 - 0.10)
    d.line([(x1 - 0.62, y0), (x1 - 0.62, y1)], "furn", layer=1)
    d.line([(x1 - 0.62, y1), (x1 - 0.95, y1 - 0.33)], "furn", layer=1)
    d.line([(x1 - 0.95, y1 - 0.33), (x1 - 0.62, y1 - 0.33)], "furn", layer=1)


def wardrobe(d, x0, y0, x1, y1):
    d.rect(x0, y0, x1, y1)
    xm = (x0 + x1) / 2
    d.line([(xm, y0), (xm, y1)], "furn", layer=1)
    n = int((y1 - y0) / 0.30)
    for i in range(1, n):
        y = y0 + i * (y1 - y0) / n
        d.line([(xm - 0.12, y - 0.06), (xm + 0.12, y + 0.06)], "furnlight", layer=1)


def toilet(d, xw, yc, s=1):
    d.rect(xw, yc - 0.20, xw + s * 0.18, yc + 0.20)
    d.poly(ellipse_pts(xw + s * 0.42, yc, 0.24, 0.18))


def basin(d, x0, y0, x1, y1, rx=0.20, ry=0.15):
    d.rect(x0, y0, x1, y1)
    d.poly(ellipse_pts((x0 + x1) / 2, (y0 + y1) / 2, rx, ry))


def shower(d, x0, y0, x1, y1, glass_at):
    d.rect(x0, y0, x1, y1, "wet", layer=0)
    d.circle(((x0 + x1) / 2, (y0 + y1) / 2), 0.05)
    if glass_at == "y0":
        d.line([(x0, y0), (x1, y0)], "glassline", layer=3)
    else:
        d.line([(x0, y1), (x1, y1)], "glassline", layer=3)


def stair(d, superior=False):
    """Escada reta: 16 espelhos de 18 cm, 15 pisos de 28 cm, largura 0,90 m."""
    ys = [round(ESC_Y0 + i * PISO_DEG, 3) for i in range(N_ESPELHOS)]
    corte_i = 7  # linha de corte da planta (~1,20 m)
    if not superior:
        for i, y in enumerate(ys):
            cls = "thin" if i <= corte_i else "hidden"
            d.line([(ESC_X0, y), (ESC_X1, y)], cls)
        yb = ys[corte_i] + 0.14
        d.line([(ESC_X0, yb - 0.10), (ESC_X1, yb + 0.10)], "thin")
        xm = (ESC_X0 + ESC_X1) / 2
        d.circle((xm, ESC_Y0 + 0.14), 0.04, "thin", layer=3)
        d.line([(xm, ESC_Y0 + 0.14), (xm, yb)], "thin")
        d.poly([(xm - 0.07, yb - 0.16), (xm + 0.07, yb - 0.16), (xm, yb - 0.02)], "arrow", layer=3)
        d.text((xm + 0.24, ESC_Y0 + 0.62), "SOBE", size=0.14, cls="small")
    else:
        for y in ys:
            if y >= VAZIO_Y0:
                d.line([(ESC_X0, y), (ESC_X1, y)], "thin")
        xm = (ESC_X0 + ESC_X1) / 2
        d.line([(xm, ESC_Y1 - 0.14), (xm, VAZIO_Y0 + 0.25)], "thin")
        d.poly([(xm - 0.07, VAZIO_Y0 + 0.39), (xm + 0.07, VAZIO_Y0 + 0.39), (xm, VAZIO_Y0 + 0.23)], "arrow", layer=3)
        d.text((xm + 0.24, ESC_Y1 - 0.62), "DESCE", size=0.14, cls="small")


def scale_bar(d, p, comp=2.0):
    """Escala gráfica de 0 a `comp` metros a partir de p, na horizontal da tela."""
    if d.plano:
        def P(t, o=0.0):
            return (p[0] + o, p[1] + t)
        up = -1
    else:
        def P(t, o=0.0):
            return (p[0] + t, p[1] + o)
        up = 1
    h = 0.07
    for i in range(int(comp)):
        cls = "barfill" if i % 2 == 0 else "barempty"
        d.poly([P(i, 0), P(i + 1, 0), P(i + 1, up * h), P(i, up * h)], cls, layer=4)
    for i in range(int(comp) + 1):
        d.text(P(i, up * 0.22), str(i), size=0.13, cls="dimtext", layer=5)
    d.text(P(comp + 0.25, up * 0.04), "m", size=0.13, cls="dimtext", layer=5)


def section_marks(d, ys=(-2.15, 21.70)):
    """Indicação do corte AA na planta (seta aponta no sentido da vista: +x)."""
    for y in ys:
        d.line([(CORTE_X, y - 0.35), (CORTE_X, y + 0.35)], "secline", layer=4)
        d.poly([(CORTE_X, y - 0.10), (CORTE_X, y + 0.10), (CORTE_X + 0.30, y)], "secarrow", layer=4)
        d.circle((CORTE_X - 0.42, y), 0.20, "secbubble", layer=4)
        d.text((CORTE_X - 0.42, y), "A", size=0.20, cls="secletter", layer=5)


# --------------------------------------------------------------------------
# PLANTA DO TÉRREO
# --------------------------------------------------------------------------
def planta_terreo():
    d = Drawing("terreo")

    # pisos (tons de fundo)
    d.area(box(0.15, 0.0, 3.85, GARAGEM_L), "floor-garage")
    d.area(box(0.15, FIM_CASA, 3.85, MURO_FUNDO), "garden")
    d.area(box(0.15, 12.00, 1.85, 14.55), "floor-wet")
    # calçada (antes do alinhamento)
    d.area(box(-0.6, -1.50, 4.6, 0.0), "sidewalk")
    d.line([(-0.6, -1.50), (4.6, -1.50)], "elevlight", layer=3)

    # paredes de divisa (até o fundo da casa) e muros do quintal
    d.wall(0.00, 0.00, 0.15, FIM_CASA)
    d.wall(3.85, 0.00, 4.00, FIM_CASA)
    d.muro(0.00, FIM_CASA, 0.15, LOTE_L)
    d.muro(3.85, FIM_CASA, 4.00, LOTE_L)
    d.muro(0.15, MURO_FUNDO, 3.85, LOTE_L)
    # pilar entre portões
    d.wall(2.85, 0.00, 2.95, 0.15)
    # fachada da casa (fundo da garagem)
    d.wall(0.15, 5.50, 3.85, 5.65)
    # fundos
    d.wall(0.15, 14.55, 3.85, 14.70)
    # lavabo + lavanderia
    d.wall(0.15, 11.90, 1.95, 12.00)
    d.wall(1.85, 12.00, 1.95, 14.55)

    # esquadrias
    window_h(d, 1.30, 2.50, 5.50, 5.65)                 # J1 sala -> garagem
    door_h(d, 2.80, 3.70, 5.50, 5.65, "x1", +1)         # P1 entrada
    door_v(d, 12.90, 13.60, 1.85, 1.95, "y1", -1)       # P3 lavabo/lavanderia
    window_h(d, 0.40, 1.60, 14.55, 14.70)               # J2 lavanderia
    sliding_h(d, 2.10, 3.70, 14.55, 14.70)              # P2 porta de correr p/ quintal

    # portões no alinhamento
    d.rect(0.15, 0.00, 2.85, 0.05, "leaf", layer=3)     # portão basculante 2,70
    d.rect(0.15, 0.05, 2.85, 1.25, "hiddenrect", layer=3)
    door(d, (3.85, 0.05), (2.95, 0.05), (3.85, 0.95))   # portão social 0,90
    d.line([(2.95, 0.05), (3.85, 0.05)], "hidden")

    # escada + guarda-corpo do lado aberto
    stair(d)
    d.line([(ESC_X1, ESC_Y0), (ESC_X1, ESC_Y1)], "rail", layer=3)
    d.rect(ESC_X0 + 0.02, 8.45, ESC_X1 - 0.02, ESC_Y1 - 0.02, "hiddenrect", layer=1)
    d.text((0.60, 9.15), "armário", size=0.11, cls="tiny")

    # mobiliário ----------------------------------------------------------
    # carro (1,80 x 4,50)
    d.poly(rounded_rect(0.42, 0.40, 2.22, 4.90, 0.30), "car")
    d.poly([(0.55, 3.55), (2.09, 3.55), (1.98, 3.05), (0.66, 3.05)], "car")
    d.poly([(0.62, 1.05), (2.02, 1.05), (1.95, 1.40), (0.69, 1.40)], "car")
    # estar
    sofa_x0, sofa_y0, sofa_x1, sofa_y1 = 1.13, 6.30, 2.03, 8.30
    d.rect(sofa_x0, sofa_y0, sofa_x1, sofa_y1)
    d.rect(sofa_x0, sofa_y0, sofa_x0 + 0.22, sofa_y1)
    d.rect(sofa_x0 + 0.22, sofa_y0, sofa_x1, sofa_y0 + 0.20)
    d.rect(sofa_x0 + 0.22, sofa_y1 - 0.20, sofa_x1, sofa_y1)
    d.line([(sofa_x0 + 0.22, 7.30), (sofa_x1, 7.30)], "furn", layer=1)
    d.rect(3.45, 6.70, 3.85, 7.90)                       # rack
    d.rect(3.70, 6.80, 3.76, 7.80, "furn", layer=1)      # TV
    d.poly(rounded_rect(2.18, 6.55, 3.18, 8.05, 0.05), "rug")
    # cozinha: geladeira + bancada (cooktop e cuba)
    d.rect(3.15, 8.95, 3.85, 9.70)
    d.line([(3.15, 8.95), (3.85, 9.70)], "furnlight", layer=1)
    d.rect(3.25, 9.70, 3.85, 13.15)
    d.rect(3.32, 10.30, 3.80, 10.90)
    for cx, cy in ((3.44, 10.44), (3.68, 10.44), (3.44, 10.76), (3.68, 10.76)):
        d.circle((cx, cy), 0.08)
    d.poly(rounded_rect(3.33, 12.05, 3.78, 12.75, 0.06))
    d.circle((3.70, 12.40), 0.03)
    # jantar (mesa 0,80 x 1,20 + 4 cadeiras)
    d.rect(0.75, 10.25, 1.55, 11.45)
    for yc in (10.55, 11.15):
        d.rect(0.30, yc - 0.21, 0.70, yc + 0.21)
        d.rect(1.60, yc - 0.21, 2.00, yc + 0.21)
    # lavabo + lavanderia
    toilet(d, 0.15, 12.40)
    basin(d, 0.15, 12.85, 0.52, 13.30, rx=0.12, ry=0.17)
    d.rect(0.25, 13.90, 0.85, 14.50)
    d.circle((0.55, 14.20), 0.22)
    d.rect(1.12, 13.97, 1.72, 14.55)
    d.rect(1.20, 14.05, 1.64, 14.38)
    # quintal: jardim, árvore, varal
    for c, r in (((3.05, 18.70), 0.75), ((0.75, 19.20), 0.40), ((3.45, 15.40), 0.30)):
        d.circle(c, r, "plant", layer=1)
    d.line([(0.55, 16.20), (0.55, 18.00)], "furnlight", layer=1)
    d.line([(0.95, 16.20), (0.95, 18.00)], "furnlight", layer=1)
    d.line([(0.40, 16.20), (1.10, 16.20)], "furn", layer=1)
    d.line([(0.40, 18.00), (1.10, 18.00)], "furn", layer=1)
    d.text((0.75, 17.10), "varal", size=0.12, cls="tiny", rot=-90)
    for y in (15.25, 15.75, 16.25):
        d.rect(2.10, y, 2.70, y + 0.35, "paver", layer=1)

    # rótulos
    areas = areas_terreo()
    d.label((3.05, 2.70), "GARAGEM", f"{fmt(areas['GARAGEM'])} m²", "4,00 × 5,50", size=0.24, sub=0.17)
    d.label((2.70, 9.05), "SALA + COZINHA", f"{fmt(areas['SALA + COZINHA'])} m²", "integradas")
    d.text((2.68, 7.30), "estar", size=0.15, cls="tiny2")
    d.text((1.15, 9.98), "jantar", size=0.15, cls="tiny2")
    d.text((2.62, 11.60), "cozinha", size=0.15, cls="tiny2")
    d.text((0.72, 13.25), "LAVABO +", size=0.15, cls="label")
    d.text((0.93, 13.25), "LAVANDERIA", size=0.15, cls="label")
    d.text((1.13, 13.25), f"{fmt(areas['LAVABO + LAVANDERIA'])} m²", size=0.13, cls="sublabel")
    d.label((2.05, 17.30), "QUINTAL", f"{fmt(areas['QUINTAL'])} m²", "área permeável")
    d.text((2.0, -1.05), "CALÇADA", size=0.15, cls="tiny2", rot=-90)
    d.text((2.4, -2.05), "RUA", size=0.20, cls="sublabel", rot=-90)

    # códigos das esquadrias
    for p, s in (((5.82, 1.90), "J1"), ((5.82, 3.25), "P1"), ((13.25, 2.18), "P3"),
                 ((14.92, 1.00), "J2"), ((14.92, 2.90), "P2")):
        d.text((p[1], p[0]), s, size=0.12, cls="code")
    d.text((1.50, -0.32), "portão basculante 2,70", size=0.12, cls="tiny", rot=-90)
    d.text((3.40, -0.32), "social 0,90", size=0.12, cls="tiny", rot=-90)

    # cotas
    dim_chain(d, 1, 4.45, [0, GARAGEM_L, FIM_CASA, LOTE_L], ext=4.0,
              labels=["5,50 garagem", "9,20 casa", "5,30 quintal"])
    dim_chain(d, 1, 4.95, [0, LOTE_L], ext=4.0, labels=["20,00 (profundidade do lote)"])
    dim_chain(d, 1, -0.40, [5.50, 5.65, ESC_Y1, 12.00, 14.55, 14.70, MURO_FUNDO], ext=0.0)
    dim_chain(d, 0, 20.45, [0, 0.15, 3.85, 4.0], ext=20.0)
    dim_chain(d, 0, 20.95, [0, 4.0], ext=20.0)
    section_marks(d)
    scale_bar(d, (4.85, -2.45))

    d.finalize()
    return d


def areas_terreo():
    salacoz = box(0.15, 5.65, 3.85, 14.55).difference(box(0.15, 11.90, 1.95, 14.55))
    return {
        "GARAGEM": box(0.15, 0.0, 3.85, GARAGEM_L).area,
        "SALA + COZINHA": salacoz.area,
        "LAVABO + LAVANDERIA": box(0.15, 12.00, 1.85, 14.55).area,
        "QUINTAL": box(0.15, FIM_CASA, 3.85, MURO_FUNDO).area,
    }


# --------------------------------------------------------------------------
# PLANTA DO PAVIMENTO SUPERIOR
# --------------------------------------------------------------------------
def areas_superior():
    circ = unary_union([box(1.05, 5.15, 1.95, ESC_Y1), box(0.15, 5.15, 1.05, VAZIO_Y0),
                        box(0.15, ESC_Y1, 1.95, 10.75)])
    return {
        "VARANDA": box(0.15, 0.0, 3.85, 1.20).area,
        "SUÍTE 1": box(0.15, 1.35, 3.85, 5.05).area,
        "BANHO 1": box(2.05, 5.15, 3.85, 7.90).area,
        "CIRCULAÇÃO": circ.area,
        "BANHO 2": box(2.05, 8.00, 3.85, 10.75).area,
        "SUÍTE 2": box(0.15, 10.85, 3.85, 14.55).area,
        "VAZIO DA ESCADA": box(ESC_X0, VAZIO_Y0, ESC_X1, ESC_Y1).area,
    }


def planta_superior():
    d = Drawing("superior")
    d.area(box(ESC_X0, VAZIO_Y0, ESC_X1, ESC_Y1), "void")
    d.area(box(2.05, 5.15, 3.85, 7.90), "floor-wet")
    d.area(box(2.05, 8.00, 3.85, 10.75), "floor-wet")
    d.area(box(0.15, 0.0, 3.85, 1.20), "floor-garage")
    # projeção da garagem/lote (para referência)
    d.rect(0.0, FIM_CASA, 4.0, LOTE_L, "ghost", layer=0)
    d.text((2.0, 17.35), "projeção do quintal (térreo)", size=0.15, cls="tiny2")

    d.wall(0.00, 0.00, 0.15, FIM_CASA)
    d.wall(3.85, 0.00, 4.00, FIM_CASA)
    d.wall(0.15, 1.20, 3.85, 1.35)     # frente suíte 1
    d.wall(0.15, 5.05, 3.85, 5.15)     # fundo suíte 1
    d.wall(1.95, 5.15, 2.05, 10.75)    # circulação | banhos
    d.wall(2.05, 7.90, 3.85, 8.00)     # banho 1 | banho 2
    d.wall(0.15, 10.75, 3.85, 10.85)   # frente suíte 2
    d.wall(0.15, 14.55, 3.85, 14.70)   # fundos

    sliding_h(d, 0.40, 2.40, 1.20, 1.35)               # P4 varanda
    door_h(d, 1.10, 1.90, 5.05, 5.15, "x0", -1)        # P5 suíte 1
    door_h(d, 2.15, 2.85, 5.05, 5.15, "x0", +1)        # P6 banho 1
    door_h(d, 0.30, 1.10, 10.75, 10.85, "x0", +1)      # P5 suíte 2
    door_h(d, 2.15, 2.85, 10.75, 10.85, "x0", -1)      # P6 banho 2
    window_h(d, 0.40, 2.40, 14.55, 14.70)              # J3 suíte 2

    # guarda-corpos (varanda e vazio)
    d.rect(0.15, 0.0, 3.85, 0.05, "rail2", layer=3)
    d.rect(ESC_X1 - 0.02, VAZIO_Y0, ESC_X1 + 0.02, ESC_Y1, "rail2", layer=3)
    d.rect(ESC_X0, VAZIO_Y0 - 0.02, ESC_X1 + 0.02, VAZIO_Y0 + 0.02, "rail2", layer=3)
    stair(d, superior=True)

    # claraboia (projeção) e exaustão dos banhos
    d.rect(0.25, VAZIO_Y0 + 0.10, 1.85, ESC_Y1 - 0.10, "skylight", layer=3)
    d.text((1.50, 6.95), "claraboia", size=0.12, cls="accenttext")
    d.text((1.66, 6.95), "(acima)", size=0.11, cls="accenttext")
    for yc in (7.35, 8.55):
        d.rect(2.95 - 0.15, yc - 0.15, 2.95 + 0.15, yc + 0.15, "hiddenrect", layer=3)
        d.line([(2.80, yc - 0.15), (3.10, yc + 0.15)], "hidden")
        d.line([(2.80, yc + 0.15), (3.10, yc - 0.15)], "hidden")

    # mobiliário
    d.rect(0.20, 0.07, 1.80, 0.30, "plant", layer=1)          # jardineira
    d.circle((3.12, 0.62), 0.22)
    d.circle((2.62, 0.62), 0.19)
    d.circle((3.60, 0.62), 0.19)
    bed_head_x1(d, 1.87, 2.41, 3.85, 3.99)
    d.rect(3.40, 1.90, 3.85, 2.36)
    d.rect(3.40, 4.04, 3.85, 4.50)
    wardrobe(d, 0.15, 1.85, 0.75, 4.15)
    # banho 1
    shower(d, 2.05, 7.00, 3.85, 7.90, "y0")
    toilet(d, 2.05, 6.50)
    basin(d, 3.35, 5.35, 3.85, 6.35, rx=0.17, ry=0.25)
    # banho 2
    shower(d, 2.05, 8.00, 3.85, 8.90, "y1")
    toilet(d, 2.05, 9.40)
    basin(d, 3.35, 9.55, 3.85, 10.55, rx=0.17, ry=0.25)
    # suíte 2
    bed_head_x1(d, 1.87, 12.01, 3.85, 13.59)
    d.rect(3.40, 11.50, 3.85, 11.96)
    d.rect(3.40, 13.64, 3.85, 14.10)
    wardrobe(d, 0.15, 11.75, 0.75, 14.05)

    a = areas_superior()
    d.label((0.95, 0.76), "VARANDA", f"{fmt(a['VARANDA'])} m²", size=0.16, sub=0.13)
    d.label((1.31, 3.20), "SUÍTE 1", f"{fmt(a['SUÍTE 1'])} m²", "3,70 × 3,70")
    d.label((3.03, 6.40), "BANHO 1", f"{fmt(a['BANHO 1'])} m²", size=0.19, sub=0.15)
    d.label((1.50, 8.55), "CIRCULAÇÃO", size=0.16, sub=0.13)
    d.label((3.03, 9.70), "BANHO 2", f"{fmt(a['BANHO 2'])} m²", size=0.19, sub=0.15)
    d.label((1.31, 12.80), "SUÍTE 2", f"{fmt(a['SUÍTE 2'])} m²", "3,70 × 3,70")
    d.text((3.40, 7.42), "box", size=0.12, cls="tiny")
    d.text((3.40, 8.47), "box", size=0.12, cls="tiny")

    for p, s in (((1.48, 1.55), "P4"), ((4.90, 1.70), "P5"), ((4.90, 2.70), "P6"),
                 ((11.00, 0.95), "P5"), ((11.00, 2.70), "P6"), ((14.38, 1.30), "J3")):
        d.text((p[1], p[0]), s, size=0.12, cls="code")

    dim_chain(d, 1, -0.40, [0, 1.20, 1.35, 5.05, 5.15, 7.90, 8.00, 10.75, 10.85, 14.55, 14.70], ext=0.0)
    dim_chain(d, 1, 4.45, [0, FIM_CASA], ext=4.0, labels=["14,70"])
    dim_chain(d, 0, 15.25, [0, 0.15, ESC_X1, 1.95, 2.05, 3.85, 4.0], ext=14.70)
    section_marks(d, ys=(-0.95, 15.95))
    scale_bar(d, (4.55, -2.45))
    d.finalize()
    return d


# --------------------------------------------------------------------------
# CORTE AA (x = 0,60, vista para a direita)
# --------------------------------------------------------------------------
def corte_aa():
    d = Drawing("corte", plano=False)
    U0 = -2.2
    # terreno (hachura) e rua
    d.area(box(U0, -0.45, 20.25, 0.0), "terrain")
    d.line([(U0, -0.15), (-1.9, -0.15), (-1.9, 0.0), (20.25, 0.0)], "ground", layer=3)

    solids = []
    # lajes de piso
    solids.append(box(0.0, -0.10, GARAGEM_L, Z_GARAGEM))
    solids.append(box(GARAGEM_L, -0.10, FIM_CASA, Z_TERREO))
    # laje do pavimento superior (com vazio da escada)
    solids.append(box(0.0, Z_LAJE_INF, VAZIO_Y0, Z_SUP))
    solids.append(box(ESC_Y1, Z_LAJE_INF, FIM_CASA, Z_SUP))
    solids.append(box(0.0, Z_VIGA_FRENTE, 0.15, Z_SUP))           # viga sobre o portão
    # laje de forro (com abertura da claraboia)
    sky0, sky1 = VAZIO_Y0 + 0.10, ESC_Y1 - 0.10
    solids.append(box(0.0, Z_FORRO, sky0, Z_LAJE_COB))
    solids.append(box(sky1, Z_FORRO, FIM_CASA, Z_LAJE_COB))
    # platibandas
    solids.append(box(0.0, Z_LAJE_COB, 0.15, Z_PLATIBANDA))
    solids.append(box(14.55, Z_LAJE_COB, FIM_CASA, Z_PLATIBANDA))
    # muretas da claraboia
    solids.append(box(sky0 - 0.10, Z_LAJE_COB, sky0, 6.80))
    solids.append(box(sky1, Z_LAJE_COB, sky1 + 0.10, 6.95))
    # paredes cortadas - térreo
    solids.append(box(5.50, Z_TERREO, 5.65, Z_LAJE_INF))                     # fachada interna
    solids.append(box(11.90, Z_TERREO, 12.00, Z_LAJE_INF))                   # lavabo
    solids.append(box(14.55, Z_TERREO, FIM_CASA, Z_TERREO + 1.40))           # fundos (peitoril)
    solids.append(box(14.55, Z_TERREO + 2.10, FIM_CASA, Z_LAJE_INF))         # verga
    # paredes cortadas - superior
    solids.append(box(1.20, Z_SUP + 2.10, 1.35, Z_FORRO))                    # verga porta varanda
    solids.append(box(5.05, Z_SUP, 5.15, Z_FORRO))
    solids.append(box(10.75, Z_SUP + 2.10, 10.85, Z_FORRO))                  # verga porta suíte 2
    solids.append(box(14.55, Z_SUP, FIM_CASA, Z_SUP + 1.00))                 # peitoril
    solids.append(box(14.55, Z_SUP + 2.20, FIM_CASA, Z_FORRO))               # verga
    # muro do fundo
    solids.append(box(MURO_FUNDO, 0.0, LOTE_L, 2.00))
    # escada (cortada)
    pts = [(ESC_Y0, Z_TERREO)]
    for i in range(N_ESPELHOS - 1):
        y = ESC_Y0 + i * PISO_DEG
        z = Z_TERREO + (i + 1) * ESPELHO
        pts += [(y, z), (y + PISO_DEG, z)]
    pts += [(ESC_Y1, Z_SUP), (ESC_Y1, Z_LAJE_INF)]
    incl = ESPELHO / PISO_DEG
    esp = 0.13 / math.cos(math.atan(incl))
    zwaist_top = Z_TERREO + incl * (ESC_Y1 - ESC_Y0) - esp
    u_floor = ESC_Y0 + esp / incl
    pts += [(ESC_Y1, zwaist_top), (u_floor, Z_TERREO)]
    solids.append(Polygon(pts))
    massa = unary_union(solids)
    d.area(massa, "cut", layer=2)

    # telhado (telha termoacústica sobre estrutura metálica leve)
    for a, b in ((0.15, sky0 - 0.10), (sky1 + 0.10, 14.55)):
        d.rect(a, Z_TELHA, b, Z_TELHA + 0.05, "roof", layer=3)
        n = max(1, int((b - a) / 1.6))
        for i in range(n + 1):
            u = a + 0.15 + i * (b - a - 0.30) / n
            d.line([(u, Z_LAJE_COB), (u, Z_TELHA)], "elev", layer=3)
    # vidro da claraboia
    d.line([(sky0 - 0.10, 6.80), (sky1 + 0.10, 6.95)], "glassline", layer=3)
    d.line([(sky0 - 0.10, 6.83), (sky1 + 0.10, 6.98)], "glassline", layer=3)

    # esquadrias no corte
    d.rect(0.0, Z_GARAGEM, 0.05, 2.40, "leaf", layer=3)                       # portão
    d.rect(0.0, Z_SUP, 0.04, Z_SUP + 1.10, "glassfill", layer=3)              # guarda-corpo varanda
    d.line([(1.255, Z_SUP), (1.255, Z_SUP + 2.10)], "glassline", layer=3)     # porta de correr P4
    d.line([(1.295, Z_SUP), (1.295, Z_SUP + 2.10)], "glassline", layer=3)
    d.line([(14.61, Z_TERREO + 1.40), (14.61, Z_TERREO + 2.10)], "glassline", layer=3)
    d.line([(14.64, Z_TERREO + 1.40), (14.64, Z_TERREO + 2.10)], "glassline", layer=3)
    d.line([(14.61, Z_SUP + 1.00), (14.61, Z_SUP + 2.20)], "glassline", layer=3)
    d.line([(14.64, Z_SUP + 1.00), (14.64, Z_SUP + 2.20)], "glassline", layer=3)
    d.rect(VAZIO_Y0 - 0.02, Z_SUP, VAZIO_Y0 + 0.02, Z_SUP + 1.10, "glassfill", layer=3)

    # em vista (além do plano de corte): corrimão da escada e guarda-corpo do vazio
    d.line([(ESC_Y0, Z_TERREO + 0.90), (ESC_Y1, Z_SUP + 0.90)], "elev", layer=3)
    d.line([(VAZIO_Y0, Z_SUP + 1.10), (ESC_Y1, Z_SUP + 1.10)], "elev", layer=3)
    for u in (VAZIO_Y0 + 1.1, VAZIO_Y0 + 2.2):
        d.line([(u, Z_SUP), (u, Z_SUP + 1.10)], "elevlight", layer=3)
    # porta P1 e janela J1 vistas ao fundo
    d.line([(5.65, 2.25), (5.50, 2.25)], "elevlight", layer=3)

    # luz natural pela claraboia: raios interrompidos no primeiro obstáculo
    from shapely.geometry import LineString, Point
    for ut, ub in ((6.85, 6.55), (7.75, 8.05), (8.65, 9.55), (9.35, 10.70)):
        top = (ut, 6.70)
        ray = LineString([top, (ub, Z_TERREO)])
        hit = ray.intersection(massa.buffer(-0.001))
        end = (ub, Z_TERREO)
        if not hit.is_empty:
            pts = []
            for g in getattr(hit, "geoms", [hit]):
                pts += list(g.coords)
            pts = [q for q in pts if q[1] < 6.5]
            if pts:
                end = max(pts, key=lambda q: q[1])
        d.line([top, end], "light", layer=1)

    # rótulos dos ambientes
    zt = Z_TERREO + 1.25
    zs = Z_SUP + 1.55
    d.text((2.75, 1.30), "GARAGEM", size=0.24, cls="label")
    d.text((2.75, 0.95), "pé-direito livre 2,50 sob a viga", size=0.14, cls="tiny2")
    d.text((6.95, 2.55), "ESCADA", size=0.20, cls="label")
    d.text((8.95, 0.80), "armário", size=0.13, cls="tiny2")
    d.text((10.90, zt), "JANTAR", size=0.20, cls="label")
    d.text((13.27, zt + 0.20), "LAVABO +", size=0.15, cls="label")
    d.text((13.27, zt - 0.05), "LAVANDERIA", size=0.15, cls="label")
    d.text((17.30, 0.70), "QUINTAL", size=0.22, cls="label")
    d.text((0.62, Z_SUP + 1.75), "VARANDA", size=0.16, cls="label")
    d.text((3.20, zs), "SUÍTE 1", size=0.22, cls="label")
    d.text((8.15, Z_SUP + 2.15), "VAZIO", size=0.18, cls="label")
    d.text((12.70, zs), "SUÍTE 2", size=0.22, cls="label")
    d.text((8.15, 7.25), "CLARABOIA", size=0.16, cls="accenttext")
    d.text((4.6, 6.45), "telha termoacústica oculta pela platibanda", size=0.13, cls="tiny2")

    # níveis
    for z, t in ((Z_CALCADA, "±0,00 calçada"), (Z_TERREO, f"+{fmt(Z_TERREO)} térreo"),
                 (Z_SUP, f"+{fmt(Z_SUP)} superior"), (Z_FORRO, f"+{fmt(Z_FORRO)} forro"),
                 (Z_PLATIBANDA, f"+{fmt(Z_PLATIBANDA)} platibanda")):
        d.poly([(20.45, z), (20.33, z + 0.13), (20.57, z + 0.13)], "levelmark", layer=4)
        d.line([(20.25, z), (20.70, z)], "dim", layer=4)
        d.text((20.75, z + 0.12), t, size=0.15, cls="dimtext", anchor="start", layer=5)

    dim_chain(d, 1, -0.65, [0.0, Z_TERREO, Z_LAJE_INF, Z_SUP, Z_FORRO, Z_LAJE_COB, Z_PLATIBANDA], ext=0.0,
              labels=[None, "2,70", None, "2,70", None, "0,75"])
    dim_chain(d, 1, -1.25, [0.0, Z_PLATIBANDA], ext=0.0)
    dim_chain(d, 0, -0.85, [0.0, GARAGEM_L, FIM_CASA, LOTE_L], toff=-0.17, labels=["5,50", "9,20", "5,30"])
    d.text((-1.05, 0.30), "rua", size=0.14, cls="tiny2")
    scale_bar(d, (-2.45, -1.55))
    return d


# --------------------------------------------------------------------------
# FACHADA FRONTAL
# --------------------------------------------------------------------------
def fachada():
    d = Drawing("fachada", plano=False)
    d.area(box(-0.6, -0.30, 4.6, 0.0), "terrain")
    d.line([(-0.6, 0.0), (4.6, 0.0)], "ground", layer=3)
    # recuos em sombra (garagem e varanda)
    d.area(box(0.15, 0.0, 3.85, Z_VIGA_FRENTE), "shadow")
    d.area(box(0.15, Z_SUP, 3.85, Z_FORRO), "recess")
    # ripado de madeira na parede da suíte (atrás da varanda)
    d.area(box(2.60, Z_SUP, 3.85, Z_FORRO), "wood")
    for i in range(1, 13):
        u = 2.60 + i * (3.85 - 2.60) / 13
        d.line([(u, Z_SUP), (u, Z_FORRO)], "slat", layer=1)
    # porta de correr de vidro da suíte
    d.area(box(0.40, Z_SUP, 2.40, Z_SUP + 2.10), "glasspane", layer=1)
    d.rect(0.40, Z_SUP, 2.40, Z_SUP + 2.10, "frame", layer=3)
    d.line([(1.40, Z_SUP), (1.40, Z_SUP + 2.10)], "frame", layer=3)
    # moldura: divisas, viga, platibanda
    frame = unary_union([box(0.0, 0.0, 0.15, Z_PLATIBANDA), box(3.85, 0.0, 4.0, Z_PLATIBANDA),
                         box(0.15, Z_VIGA_FRENTE, 3.85, Z_SUP), box(0.15, Z_FORRO, 3.85, Z_PLATIBANDA)])
    d.area(frame, "facade", layer=2)
    d.line([(0.0, Z_LAJE_COB + 0.0), (4.0, Z_LAJE_COB)], "elevlight", layer=3)
    # guarda-corpo de vidro
    d.area(box(0.15, Z_SUP, 3.85, Z_SUP + 1.10), "glassrail", layer=3)
    d.line([(0.15, Z_SUP + 1.10), (3.85, Z_SUP + 1.10)], "frame", layer=3)
    for u0 in (0.6, 2.2):
        d.line([(u0, Z_SUP + 0.20), (u0 + 0.35, Z_SUP + 0.85)], "reflect", layer=3)
        d.line([(u0 + 0.18, Z_SUP + 0.20), (u0 + 0.42, Z_SUP + 0.62)], "reflect", layer=3)
    # jardineira atrás do vidro
    for c in ((0.45, Z_SUP + 0.55), (0.85, Z_SUP + 0.65), (1.30, Z_SUP + 0.52), (1.65, Z_SUP + 0.60)):
        d.circle(c, 0.22, "plantelev", layer=3)
    # portões
    d.area(box(0.15, 0.0, 2.85, 2.40), "gate", layer=3)
    d.area(box(2.95, 0.0, 3.85, 2.40), "gate", layer=3)
    d.area(box(2.85, 0.0, 2.95, Z_VIGA_FRENTE), "facade", layer=3)
    for a, b in ((0.15, 2.85), (2.95, 3.85)):
        n = int((b - a) / 0.11)
        for i in range(1, n):
            u = a + i * (b - a) / n
            d.line([(u, 0.05), (u, 2.35)], "slat2", layer=3)
        d.rect(a, 0.0, b, 2.40, "frame", layer=3)
    d.line([(3.10, 1.00), (3.10, 1.25)], "frame", layer=3)

    # anotações de materiais (lado direito)
    notes = [
        (6.15, (3.60, 6.15), "Platibanda — reboco e pintura"),
        (5.30, (2.15, 4.95), "Porta de correr em vidro (suíte 1)"),
        (4.55, (3.30, 4.55), "Ripado de madeira"),
        (3.55, (3.60, 3.55), "Guarda-corpo em vidro laminado, h = 1,10"),
        (1.55, (2.45, 1.55), "Portão basculante ripado, 2,70 × 2,40"),
        (0.75, (3.55, 0.75), "Portão social, 0,90 × 2,40"),
    ]
    for z, (u0, z0), t in notes:
        d.line([(u0, z0), (4.35, z), (4.55, z)], "leader", layer=4)
        d.circle((u0, z0), 0.035, "leaderdot", layer=4)
        d.text((4.62, z), t, size=0.15, cls="note", anchor="start")

    dim_chain(d, 0, -0.55, [0.0, 0.15, 3.85, 4.0], ext=0.0, toff=-0.17)
    dim_chain(d, 0, -1.00, [0.0, 4.0], ext=0.0, toff=-0.17)
    dim_chain(d, 1, -0.45, [0.0, Z_VIGA_FRENTE, Z_SUP, Z_FORRO, Z_PLATIBANDA], ext=0.0)
    dim_chain(d, 1, -0.95, [0.0, Z_PLATIBANDA], ext=0.0)
    scale_bar(d, (5.0, -0.95))
    return d


# --------------------------------------------------------------------------
# Renderização SVG
# --------------------------------------------------------------------------
STYLE_STANDALONE = """
  .bg{fill:#ffffff}
  text{font-family:'Barlow Condensed','Arial Narrow','Helvetica Neue',Arial,sans-serif}
  .wall,.cut{fill:#22262b;stroke:#22262b;stroke-width:.5}
  .muro{fill:#9aa1a8;stroke:#5f666d;stroke-width:.5}
  .facade{fill:#e9e6df;stroke:#22262b;stroke-width:1}
  .floor-garage{fill:#eef0f1}
  .floor-wet{fill:#e6eef3}
  .wet{fill:#d8e6ee;stroke:#7d8a94;stroke-width:.6}
  .garden{fill:#e4efdc}
  .sidewalk{fill:#eceae5}
  .void{fill:#f4f5f6;stroke:none}
  .ghost{fill:none;stroke:#b8bec4;stroke-width:.7;stroke-dasharray:4 3}
  .terrain{fill:url(#HATCH);stroke:none}
  .furn,.car,.rug,.paver{fill:none;stroke:#8b939b;stroke-width:.8}
  .rug{stroke-dasharray:2 2}
  .furnlight{fill:none;stroke:#b2b8be;stroke-width:.6}
  .plant{fill:#cfe3c4;stroke:#7fa070;stroke-width:.8}
  .door{fill:none;stroke:#22262b;stroke-width:1.2}
  .swing{fill:none;stroke:#22262b;stroke-width:.6}
  .win{fill:none;stroke:#22262b;stroke-width:.7}
  .glass{fill:none;stroke:#2f6db3;stroke-width:.7}
  .glassline{fill:none;stroke:#2f6db3;stroke-width:.9}
  .glassfill{fill:#2f6db3;stroke:#2f6db3;stroke-width:.4}
  .leaf{fill:#ffffff;stroke:#22262b;stroke-width:.8}
  .thin{fill:none;stroke:#22262b;stroke-width:.7}
  .hidden{fill:none;stroke:#59616a;stroke-width:.6;stroke-dasharray:4 3}
  .hiddenrect{fill:none;stroke:#8b939b;stroke-width:.6;stroke-dasharray:4 3}
  .arrow{fill:#22262b;stroke:none}
  .rail{fill:none;stroke:#22262b;stroke-width:1.4}
  .rail2{fill:#ffffff;stroke:#22262b;stroke-width:.7}
  .skylight{fill:none;stroke:#2f6db3;stroke-width:.9;stroke-dasharray:7 3 1.5 3}
  .dim,.dimext{fill:none;stroke:#5c636b;stroke-width:.55}
  .dimtick{fill:none;stroke:#22262b;stroke-width:1.1}
  .dimtext{fill:#3b4249;font-family:'IBM Plex Mono',Menlo,Consolas,monospace}
  .label{fill:#15181b;font-weight:600;letter-spacing:.04em}
  .sublabel{fill:#4f575f}
  .small,.tiny,.tiny2{fill:#59616a}
  .code{fill:#2f6db3;font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-weight:600}
  .accenttext{fill:#2f6db3;font-weight:600;letter-spacing:.04em}
  .secline{fill:none;stroke:#c2410c;stroke-width:2}
  .secarrow{fill:#c2410c;stroke:none}
  .secbubble{fill:#ffffff;stroke:#c2410c;stroke-width:1.2}
  .secletter{fill:#c2410c;font-weight:700}
  .ground{fill:none;stroke:#22262b;stroke-width:1.6}
  .roof{fill:#7b838b;stroke:#22262b;stroke-width:.5}
  .elev{fill:none;stroke:#5c636b;stroke-width:.8}
  .elevlight{fill:none;stroke:#9aa1a8;stroke-width:.6}
  .light{fill:none;stroke:#e0a400;stroke-width:1;stroke-dasharray:6 4}
  .levelmark{fill:#22262b;stroke:none}
  .shadow{fill:#3a3f45}
  .recess{fill:#d7d3cb}
  .wood{fill:#b9855a}
  .slat{stroke:#7e5532;stroke-width:1.2}
  .glasspane{fill:#a9c4dc}
  .frame{fill:none;stroke:#22262b;stroke-width:.9}
  .glassrail{fill:#cfe0ee;fill-opacity:.55;stroke:#22262b;stroke-width:.6}
  .reflect{stroke:#ffffff;stroke-width:1.4;stroke-opacity:.9}
  .plantelev{fill:#8fb37c;stroke:#5f8a4f;stroke-width:.6}
  .gate{fill:#4a5057}
  .slat2{stroke:#2a2e33;stroke-width:1.6}
  .leader{fill:none;stroke:#5c636b;stroke-width:.6}
  .leaderdot{fill:#22262b}
  .note{fill:#2b3137}
  .barfill{fill:#22262b;stroke:#22262b;stroke-width:.6}
  .barempty{fill:#ffffff;stroke:#22262b;stroke-width:.6}
"""

HATCH_DEF = (
    '<defs><pattern id="{id}" width="7" height="7" patternUnits="userSpaceOnUse" '
    'patternTransform="rotate(45)"><rect width="7" height="7" class="hatchbg"/>'
    '<line x1="0" y1="0" x2="0" y2="7" class="hatchline"/></pattern></defs>'
)


def _bounds(d):
    xs, ys = [], []
    for it in d.items:
        k = it["kind"]
        if k in ("line", "poly"):
            for p in it["pts"]:
                xs.append(p[0]); ys.append(p[1])
        elif k in ("circle", "arc"):
            xs += [it["c"][0] - it["r"], it["c"][0] + it["r"]]
            ys += [it["c"][1] - it["r"], it["c"][1] + it["r"]]
        elif k == "area" and not it["geom"].is_empty:
            b = it["geom"].bounds
            xs += [b[0], b[2]]; ys += [b[1], b[3]]
        elif k == "text":
            xs.append(it["p"][0]); ys.append(it["p"][1])
    return min(xs), min(ys), max(xs), max(ys)


class SvgMap:
    def __init__(self, d, s, margin, extra=(0, 0, 0, 0), xrange=None):
        self.d, self.s = d, s
        x0, y0, x1, y1 = _bounds(d)
        if d.plano:   # tela: X = y, Y = x
            self.minX, self.maxX = y0 - margin - extra[0], y1 + margin + extra[2]
            self.minY, self.maxY = x0 - margin - extra[1], x1 + margin + extra[3]
        else:         # tela: X = u, Y = -z
            self.minX, self.maxX = x0 - margin - extra[0], x1 + margin + extra[2]
            self.minY, self.maxY = -y1 - margin - extra[1], -y0 + margin + extra[3]
        if xrange:
            self.minX, self.maxX = xrange
        self.W = (self.maxX - self.minX) * s
        self.H = (self.maxY - self.minY) * s

    def __call__(self, p):
        if self.d.plano:
            X, Y = p[1], p[0]
        else:
            X, Y = p[0], -p[1]
        return ((X - self.minX) * self.s, (Y - self.minY) * self.s)


def _path_from_geom(g, T):
    polys = [g] if isinstance(g, Polygon) else list(getattr(g, "geoms", []))
    out = []
    for pg in polys:
        if not isinstance(pg, Polygon) or pg.is_empty:
            continue
        for ring in [pg.exterior] + list(pg.interiors):
            pts = [T(p) for p in ring.coords]
            out.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z")
    return " ".join(out)


def to_svg(d, s=56, margin=0.35, uid="d", standalone=False, extra=(0, 0, 0, 0), css_class="dwg", xrange=None):
    T = SvgMap(d, s, margin, extra, xrange)
    out = []
    hatch_id = f"hatch-{uid}"
    for it in sorted(d.items, key=lambda i: i["layer"]):
        k, c = it["kind"], it["cls"]
        if k == "area":
            if it["geom"].is_empty:
                continue
            extra_attr = f' fill="url(#{hatch_id})"' if c == "terrain" else ""
            out.append(f'<path class="{c}"{extra_attr} fill-rule="evenodd" d="{_path_from_geom(it["geom"], T)}"/>')
        elif k in ("line", "poly"):
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(T, it["pts"]))
            tag = "polyline" if k == "line" else "polygon"
            out.append(f'<{tag} class="{c}" points="{pts}"/>')
        elif k == "circle":
            x, y = T(it["c"])
            out.append(f'<circle class="{c}" cx="{x:.1f}" cy="{y:.1f}" r="{it["r"] * s:.1f}"/>')
        elif k == "arc":
            a0, a1 = it["a0"], it["a1"]
            da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            n = 18
            pts = [(it["c"][0] + it["r"] * math.cos(a0 + da * i / n), it["c"][1] + it["r"] * math.sin(a0 + da * i / n))
                   for i in range(n + 1)]
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(T, pts))
            out.append(f'<polyline class="{c}" points="{pts}"/>')
        elif k == "text":
            if not it["s"]:
                continue
            x, y = T(it["p"])
            fs = it["size"] * s
            anchor = {"middle": "middle", "start": "start", "end": "end"}[it["anchor"]]
            rot = f' transform="rotate({it["rot"]} {x:.1f} {y:.1f})"' if it["rot"] else ""
            out.append(f'<text class="{c}" x="{x:.1f}" y="{y:.1f}" font-size="{fs:.1f}" text-anchor="{anchor}" '
                       f'dominant-baseline="central"{rot}>{html.escape(it["s"])}</text>')
    body = "\n".join(out)
    defs = HATCH_DEF.replace("{id}", hatch_id)
    vb = f'0 0 {T.W:.0f} {T.H:.0f}'
    if standalone:
        style = STYLE_STANDALONE + ".hatchbg{fill:#f1efe9}.hatchline{stroke:#b9b2a5;stroke-width:1}"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{T.W:.0f}" height="{T.H:.0f}">'
                f'<style>{style}</style>{defs}<rect class="bg" x="0" y="0" width="{T.W:.0f}" height="{T.H:.0f}"/>'
                f'{body}</svg>'), T
    return (f'<svg class="{css_class}" xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
            f'data-w="{T.W:.0f}" data-h="{T.H:.0f}" role="img">{defs}{body}</svg>'), T


# --------------------------------------------------------------------------
# DXF
# --------------------------------------------------------------------------
LAYER_OF = {
    "wall": "PAREDES", "cut": "CORTE-ELEMENTOS", "muro": "MUROS", "facade": "FACHADA",
    "door": "ESQUADRIAS", "swing": "ESQUADRIAS", "win": "ESQUADRIAS", "glass": "ESQUADRIAS",
    "glassline": "ESQUADRIAS", "leaf": "ESQUADRIAS", "glassfill": "ESQUADRIAS", "frame": "ESQUADRIAS",
    "dim": "COTAS", "dimext": "COTAS", "dimtick": "COTAS", "dimtext": "COTAS", "levelmark": "COTAS",
    "label": "TEXTOS", "sublabel": "TEXTOS", "small": "TEXTOS", "tiny": "TEXTOS", "tiny2": "TEXTOS",
    "code": "TEXTOS", "accenttext": "TEXTOS", "note": "TEXTOS",
    "thin": "ESCADA", "hidden": "PROJECOES", "hiddenrect": "PROJECOES", "skylight": "PROJECOES",
    "arrow": "ESCADA", "rail": "ESCADA", "rail2": "ESCADA",
    "secline": "CORTE-INDICACAO", "secarrow": "CORTE-INDICACAO", "secbubble": "CORTE-INDICACAO",
    "secletter": "CORTE-INDICACAO",
}
LAYER_COLORS = {"PAREDES": 7, "MUROS": 8, "ESQUADRIAS": 5, "MOBILIARIO": 8, "COTAS": 3, "TEXTOS": 7,
                "ESCADA": 7, "PROJECOES": 9, "CORTE-INDICACAO": 1, "CORTE-ELEMENTOS": 7, "FACHADA": 7,
                "PISOS": 9, "VISTAS": 8}


def to_dxf(drawings, path):
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6  # metros
    for name, color in LAYER_COLORS.items():
        doc.layers.add(name, color=color)
    msp = doc.modelspace()

    for d, (ox, oy), titulo in drawings:
        if d.plano:
            def T(p, ox=ox, oy=oy):
                return (ox + p[1], oy - p[0])
            rot_off = -90.0
        else:
            def T(p, ox=ox, oy=oy):
                return (ox + p[0], oy + p[1])
            rot_off = 0.0
        for it in d.items:
            k, c = it["kind"], it["cls"]
            layer = LAYER_OF.get(c, "MOBILIARIO" if it["layer"] == 1 else ("PISOS" if it["layer"] == 0 else "VISTAS"))
            if k == "area":
                g = it["geom"]
                if g.is_empty or c not in ("wall", "cut", "muro", "facade"):
                    continue
                polys = [g] if isinstance(g, Polygon) else list(g.geoms)
                hatch = msp.add_hatch(color=LAYER_COLORS.get(layer, 7), dxfattribs={"layer": layer})
                if c in ("muro",):
                    hatch.set_pattern_fill("ANSI31", scale=0.02)
                for pg in polys:
                    for j, ring in enumerate([pg.exterior] + list(pg.interiors)):
                        pts = [T(p) for p in ring.coords]
                        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
                        hatch.paths.add_polyline_path(pts, is_closed=True, flags=1 if j == 0 else 0)
                if c == "facade":
                    msp.delete_entity(hatch)
            elif k == "line":
                msp.add_lwpolyline([T(p) for p in it["pts"]], dxfattribs={"layer": layer})
            elif k == "poly":
                msp.add_lwpolyline([T(p) for p in it["pts"]], close=True, dxfattribs={"layer": layer})
            elif k == "circle":
                msp.add_circle(T(it["c"]), it["r"], dxfattribs={"layer": layer})
            elif k == "arc":
                a0, a1 = it["a0"], it["a1"]
                da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
                s_, e_ = (a0, a0 + da) if da > 0 else (a0 + da, a0)
                msp.add_arc(T(it["c"]), it["r"], math.degrees(s_) + rot_off, math.degrees(e_) + rot_off,
                            dxfattribs={"layer": layer})
            elif k == "text" and it["s"]:
                al = {"middle": TextEntityAlignment.MIDDLE_CENTER, "start": TextEntityAlignment.MIDDLE_LEFT,
                      "end": TextEntityAlignment.MIDDLE_RIGHT}[it["anchor"]]
                t = msp.add_text(it["s"], height=it["size"] * 0.8,
                                 dxfattribs={"layer": layer, "rotation": -it["rot"]})
                t.set_placement(T(it["p"]), align=al)
        # título de cada desenho
        b = _bounds(d)
        if d.plano:
            tx, ty = ox + b[1], oy - b[2] - 0.9
        else:
            tx, ty = ox + b[0], oy + b[1] - 0.9
        msp.add_text(titulo, height=0.35, dxfattribs={"layer": "TEXTOS"}).set_placement((tx, ty))
    doc.saveas(path)


# --------------------------------------------------------------------------
# Quadro de áreas e índices
# --------------------------------------------------------------------------
def quadro():
    at, asup = areas_terreo(), areas_superior()
    lote = LOTE_W * LOTE_L
    terreo_constr = LOTE_W * FIM_CASA                 # inclui garagem coberta
    sup_constr = LOTE_W * FIM_CASA                    # inclui varanda e vazio
    total = terreo_constr + sup_constr
    util_t = at["GARAGEM"] + at["SALA + COZINHA"] + at["LAVABO + LAVANDERIA"]
    util_s = sum(v for k, v in asup.items() if k != "VAZIO DA ESCADA")
    return dict(
        terreo=[("Garagem (coberta)", at["GARAGEM"]), ("Sala + cozinha integradas (inclui escada)", at["SALA + COZINHA"]),
                ("Lavabo + lavanderia", at["LAVABO + LAVANDERIA"])],
        superior=[("Varanda", asup["VARANDA"]), ("Suíte 1 (quarto)", asup["SUÍTE 1"]), ("Banho suíte 1", asup["BANHO 1"]),
                  ("Circulação", asup["CIRCULAÇÃO"]), ("Banho suíte 2", asup["BANHO 2"]), ("Suíte 2 (quarto)", asup["SUÍTE 2"])],
        quintal=at["QUINTAL"], vazio=asup["VAZIO DA ESCADA"],
        util_t=util_t, util_s=util_s, terreo_constr=terreo_constr, sup_constr=sup_constr, total=total,
        lote=lote, to=terreo_constr / lote, ca=total / lote, perm=at["QUINTAL"] / lote,
    )


# --------------------------------------------------------------------------
# Saídas
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Textos do memorial (usados na página, na prancha e no README)
# --------------------------------------------------------------------------
PROGRAMA = [
    ("Garagem de 5,50 m ocupando toda a frente",
     "Garagem coberta de 4,00 × 5,50 m (3,70 m livres entre paredes), com portão basculante de 2,70 m "
     "e portão social de 0,90 m. Cabe um carro de até 5 m, com espaço para abrir a porta e passar ao lado."),
    ("Sala e cozinha conjugadas",
     "Um só ambiente de 28,16 m² com estar, mesa para 4 e cozinha linear (3,45 m de bancada mais a geladeira), "
     "aberto para o quintal por uma porta de correr de vidro."),
    ("Lavabo junto com a lavanderia",
     "Ambiente único de 4,34 m² nos fundos com vaso, lavatório, tanque e máquina de lavar. "
     "A janela para o quintal garante ventilação natural."),
    ("Duas suítes",
     "No pavimento superior, duas suítes iguais de 3,70 × 3,70 m (13,69 m²), cada uma com banheiro de 4,95 m². "
     "A suíte da frente tem varanda de 4,44 m² sobre a garagem."),
]

PARTIDO = [
    ("Por que sobrado",
     "Com 3,70 m livres de largura, o programa não cabe num pavimento só sem acabar com o quintal. "
     "No sobrado, o térreo fica com a parte social e o pavimento de cima com as suítes."),
    ("Paredes laterais sem janelas",
     "O Código Civil (art. 1.301) proíbe abrir janelas a menos de 1,5 m da divisa, e num lote de 4 m as duas "
     "paredes laterais estão na divisa. Por isso toda a luz entra pela frente, pelos fundos e por uma claraboia "
     "sobre a escada, que funciona como poço de luz para a sala e para a circulação."),
    ("Escada reta encostada na divisa",
     "A escada ocupa só 0,90 m de largura e deixa a sala livre. São 16 degraus com espelho de 18 cm e piso de "
     "28 cm (2 × 18 + 28 = 64 cm, dentro da fórmula de Blondel) e guarda-corpo de 1,10 m. "
     "Embaixo do trecho mais alto há um armário."),
    ("Hidráulica concentrada",
     "O banheiro da suíte 2 fica sobre a bancada da cozinha e o da suíte 1 desce pela mesma parede, com um "
     "rebaixo de forro de gesso na sala para a tubulação. Cozinha, lavabo e lavanderia ficam nos fundos, perto "
     "da saída de esgoto."),
    ("Suíte sobre a garagem",
     "A suíte 1 e a varanda avançam sobre a garagem. Assim o carro fica coberto e sobram 5,30 m de quintal "
     "nos fundos para jardim, varal e área permeável."),
]

MEMORIAL = [
    ("Alturas", "Pé-direito de 2,70 m nos dois pavimentos e 2,88 m de piso a piso. Na garagem, 2,80 m livres "
                "sob a laje e 2,50 m sob a viga do portão. Altura total até a platibanda: 6,60 m."),
    ("Estrutura", "Concreto armado, com pilares embutidos nas paredes de divisa e lajes vencendo o vão de 3,70 m. "
                  "Uma alternativa é alvenaria estrutural com blocos de 14 cm. O dimensionamento é do projeto "
                  "estrutural, depois da sondagem do terreno."),
    ("Paredes", "Paredes de divisa e externas com 15 cm acabadas, internas com 10 cm."),
    ("Cobertura", "Laje de forro mais telha termoacústica com cerca de 10% de caimento, escondida pela platibanda "
                  "e com calha interna. Claraboia de vidro laminado sobre a escada, de preferência com abertura "
                  "para tirar o ar quente."),
    ("Ventilação dos banheiros", "Os banheiros do pavimento superior ficam no miolo da casa: ventilação por "
                                 "exaustor com duto até a cobertura ou por domus ventilado."),
    ("Iluminação", "As aberturas dos quartos e da sala ficam em torno de 1/6 da área de piso, a proporção que muitos "
                   "códigos de obras pedem para ambientes de permanência prolongada; a claraboia complementa a "
                   "sala. Confira o índice exigido no código do seu município."),
    ("Área permeável", "Quintal ajardinado e, se possível, piso drenante na garagem (concregrama ou "
                       "intertravado permeável)."),
]

VERIFICAR = [
    ("Recuo frontal", "Muitas prefeituras exigem recuo frontal de 4 a 5 m. A garagem cumpre esse papel no térreo, "
                      "mas algumas cidades não permitem construir o pavimento superior sobre o recuo. Nesse caso, a "
                      "casa precisa avançar sobre o quintal (que cai de 5,30 m para cerca de 1,50 m)."),
    ("Índices urbanísticos", "Taxa de ocupação de 73,5%, coeficiente de aproveitamento de 1,47 e permeabilidade "
                             "de até 23,8%. Compare com o zoneamento do lote."),
    ("Aprovação", "Este é um anteprojeto. Para construir, é preciso o projeto legal assinado por arquiteto ou "
                  "engenheiro (RRT/ART), além dos projetos estrutural, elétrico e hidrossanitário."),
]

ESQUADRIAS = [
    ("P1", "Porta de entrada, de giro", "0,90 × 2,10", "—", 1),
    ("P2", "Porta de correr de vidro, 2 folhas (cozinha → quintal)", "1,60 × 2,10", "—", 1),
    ("P3", "Porta de giro (lavabo + lavanderia)", "0,70 × 2,10", "—", 1),
    ("P4", "Porta de correr de vidro, 2 folhas (suíte 1 → varanda)", "2,00 × 2,10", "—", 1),
    ("P5", "Porta de giro (suítes)", "0,80 × 2,10", "—", 2),
    ("P6", "Porta de giro (banheiros)", "0,70 × 2,10", "—", 2),
    ("J1", "Janela de correr (sala → garagem)", "1,20 × 1,20", "1,00", 1),
    ("J2", "Janela basculante (lavanderia)", "1,20 × 0,70", "1,40", 1),
    ("J3", "Janela de correr (suíte 2)", "2,00 × 1,20", "1,00", 1),
    ("PG", "Portão basculante ripado", "2,70 × 2,40", "—", 1),
    ("PS", "Portão social ripado", "0,90 × 2,40", "—", 1),
]

FONTS = ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700"
         "&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;600&display=swap")

# --------------------------------------------------------------------------
# Página HTML (artifact) - cores por tokens, tema claro e escuro
# --------------------------------------------------------------------------
PAGE_CSS = r"""
/* Layout: prancha de desenho — desenhos largos alinhados pelo mesmo eixo de profundidade, texto em coluna estreita */
:root{
  --bg:#e9ece8; --sheet:#fbfbf9; --ink:#1b1f23; --ink2:#4a535b; --rule:#c6ccc8;
  --poche:#22262a; --furn:#8b939a; --furn2:#b4bac0; --accent:#2a60a6; --mark:#c2410c; --sun:#cf9300;
  --garage:#edefef; --wet:#e1ebf1; --wetbox:#d3e2ec; --garden:#dcebcf; --gardenline:#7a9c6b; --walk:#e5e3dd;
  --terrainbg:#eeece6; --terrainline:#b8b1a3; --roof:#7b838b; --muro:#9aa1a8; --murol:#5f666d;
  --facade:#e6e2da; --recess:#d4d0c7; --shadow:#3a3f45; --wood:#b9855a; --woodline:#7e5532;
  --gate:#4a5057; --gateline:#2a2e33; --glasspane:#a9c4dc; --glassrail:#cfe0ee; --plant:#8fb37c; --reflect:#ffffff;
  --f-display:"Barlow Condensed","Arial Narrow","Roboto Condensed",sans-serif;
  --f-body:"Source Sans 3","Segoe UI",system-ui,-apple-system,sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#111417; --sheet:#181c20; --ink:#e4e8eb; --ink2:#a2abb3; --rule:#2e353b;
  --poche:#dde2e6; --furn:#76808a; --furn2:#4f575f; --accent:#79adf0; --mark:#f4844a; --sun:#f2b733;
  --garage:#1f2428; --wet:#1a2630; --wetbox:#21313d; --garden:#1c2a1b; --gardenline:#5f8a52; --walk:#22252a;
  --terrainbg:#1d2023; --terrainline:#3c4248; --roof:#8a939b; --muro:#59626a; --murol:#8a939b;
  --facade:#2f3338; --recess:#262a2f; --shadow:#0c0e10; --wood:#9a6b45; --woodline:#5f3f22;
  --gate:#5a626a; --gateline:#3a4046; --glasspane:#3d5a75; --glassrail:#2c4256; --plant:#5f8a52; --reflect:#c9d8e6;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#111417; --sheet:#181c20; --ink:#e4e8eb; --ink2:#a2abb3; --rule:#2e353b;
  --poche:#dde2e6; --furn:#76808a; --furn2:#4f575f; --accent:#79adf0; --mark:#f4844a; --sun:#f2b733;
  --garage:#1f2428; --wet:#1a2630; --wetbox:#21313d; --garden:#1c2a1b; --gardenline:#5f8a52; --walk:#22252a;
  --terrainbg:#1d2023; --terrainline:#3c4248; --roof:#8a939b; --muro:#59626a; --murol:#8a939b;
  --facade:#2f3338; --recess:#262a2f; --shadow:#0c0e10; --wood:#9a6b45; --woodline:#5f3f22;
  --gate:#5a626a; --gateline:#3a4046; --glasspane:#3d5a75; --glassrail:#2c4256; --plant:#5f8a52; --reflect:#c9d8e6;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--f-body);font-size:16px;line-height:1.55;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:28px 56px}
.wrap{max-width:1240px;margin:0 auto;display:grid;gap:40px}
h1,h2,h3{font-family:var(--f-display);text-wrap:balance;margin:0;letter-spacing:.01em}
h1{font-size:clamp(2.6rem,6vw,4.2rem);font-weight:700;line-height:.95;text-transform:uppercase}
h2{font-size:1.65rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em}
h3{font-size:1.15rem;font-weight:600}
p{margin:0}
.eyebrow{font-family:var(--f-mono);font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;color:var(--ink2)}
.lede{max-width:62ch;color:var(--ink2);font-size:1.06rem}
.mono{font-family:var(--f-mono);font-variant-numeric:tabular-nums}

/* cabeçalho + carimbo */
.head{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:28px;align-items:end}
.head .intro{display:grid;gap:14px}
.carimbo{border:1.5px solid var(--ink);background:var(--sheet);display:grid;grid-template-columns:1fr 1fr}
.carimbo div{padding:8px 12px;border-right:1px solid var(--rule);border-bottom:1px solid var(--rule);min-width:0}
.carimbo div:nth-child(2n){border-right:0}
.carimbo div.full{grid-column:1/-1;border-right:0}
.carimbo div:nth-last-child(-n+2):not(.full){border-bottom:0}
.carimbo dt{font-family:var(--f-mono);font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink2)}
.carimbo dd{margin:2px 0 0;font-family:var(--f-display);font-size:1.25rem;font-weight:600;font-variant-numeric:tabular-nums}

/* programa */
.programa{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;border-top:1.5px solid var(--ink)}
.programa li{list-style:none;padding:14px 16px 4px 0;display:grid;gap:6px;align-content:start;min-width:0}
.programa li+li{padding-left:16px;border-left:1px solid var(--rule)}
.programa ol{display:contents}
.programa .ok{font-family:var(--f-mono);font-size:.72rem;color:var(--accent);letter-spacing:.08em;text-transform:uppercase}
.programa p{font-size:.95rem;color:var(--ink2)}

/* desenhos */
.set{display:grid;gap:18px}
figure{margin:0;background:var(--sheet);border:1px solid var(--rule);display:grid}
figcaption{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 16px;
  padding:10px 16px;border-bottom:1px solid var(--rule)}
figcaption h3{font-size:1.2rem;text-transform:uppercase;letter-spacing:.05em}
figcaption span{font-family:var(--f-mono);font-size:.74rem;color:var(--ink2)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.dwg{display:block;width:100%;height:auto;min-width:900px}
.dwg.small{min-width:460px;max-width:640px;margin:0 auto}
.hint{display:none;font-family:var(--f-mono);font-size:.72rem;color:var(--ink2);padding:6px 16px 10px}
@media (max-width:900px){.hint{display:block}}
.legend{display:flex;flex-wrap:wrap;gap:8px 22px;font-size:.85rem;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{display:inline-block;width:22px;height:10px}
.lg-wall{background:var(--poche)}
.lg-glass{border-top:2px solid var(--accent);height:0!important;margin-top:4px}
.lg-sec{border-top:3px solid var(--mark);height:0!important}
.lg-sun{border-top:2px dashed var(--sun);height:0!important}
.lg-proj{border-top:1.5px dashed var(--ink2);height:0!important}

.duo{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;align-items:start}

/* tabelas */
table{border-collapse:collapse;width:100%;font-size:.94rem}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-family:var(--f-mono);font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink2);font-weight:500}
td.n,th.n{text-align:right;font-family:var(--f-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
tr.grp td{font-family:var(--f-display);font-weight:600;text-transform:uppercase;letter-spacing:.05em;padding-top:14px;border-bottom:1.5px solid var(--ink)}
tr.sum td{font-weight:600}
tr.total td{font-family:var(--f-display);font-size:1.15rem;font-weight:700;border-bottom:1.5px solid var(--ink);border-top:1.5px solid var(--ink)}
.tablebox{background:var(--sheet);border:1px solid var(--rule);padding:6px 16px 16px;min-width:0}
.tablebox .scroll table{min-width:520px}
.indices{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}
.indices div{border-top:1.5px solid var(--ink);padding-top:6px}
.indices b{display:block;font-family:var(--f-display);font-size:1.5rem;font-variant-numeric:tabular-nums}
.indices small{color:var(--ink2);font-size:.8rem}

/* textos */
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:22px 40px}
.item{display:grid;gap:4px;min-width:0;align-content:start}
.item p{color:var(--ink2);max-width:62ch}
.aviso{background:var(--sheet);border:1.5px solid var(--mark);padding:18px 20px;display:grid;gap:14px}
.aviso h2{color:var(--mark)}
.files{display:grid;gap:6px;font-size:.95rem;color:var(--ink2)}
.files code{font-family:var(--f-mono);font-size:.85rem;color:var(--ink)}
section{display:grid;gap:18px}

@media (max-width:860px){
  .head{grid-template-columns:1fr}
  .programa{grid-template-columns:1fr 1fr}
  .programa li:nth-child(3){padding-left:0;border-left:0}
  .duo{grid-template-columns:1fr}
}
@media (max-width:520px){
  .programa{grid-template-columns:1fr}
  .programa li+li{padding-left:0;border-left:0;border-top:1px solid var(--rule)}
  .indices b{font-size:1.25rem}
}

/* classes dos desenhos */
.dwg text{font-family:var(--f-display)}
.dwg .wall,.dwg .cut{fill:var(--poche);stroke:var(--poche);stroke-width:.5}
.dwg .muro{fill:var(--muro);stroke:var(--murol);stroke-width:.5}
.dwg .facade{fill:var(--facade);stroke:var(--ink);stroke-width:1}
.dwg .floor-garage{fill:var(--garage)}
.dwg .floor-wet{fill:var(--wet)}
.dwg .wet{fill:var(--wetbox);stroke:var(--furn);stroke-width:.6}
.dwg .garden{fill:var(--garden)}
.dwg .sidewalk{fill:var(--walk)}
.dwg .void{fill:var(--bg)}
.dwg .ghost{fill:none;stroke:var(--furn2);stroke-width:.7;stroke-dasharray:4 3}
.dwg .hatchbg{fill:var(--terrainbg)}
.dwg .hatchline{stroke:var(--terrainline);stroke-width:1}
.dwg .furn,.dwg .car,.dwg .rug,.dwg .paver{fill:none;stroke:var(--furn);stroke-width:.8}
.dwg .rug{stroke-dasharray:2 2}
.dwg .furnlight{fill:none;stroke:var(--furn2);stroke-width:.6}
.dwg .plant{fill:var(--garden);stroke:var(--gardenline);stroke-width:.8}
.dwg .door{fill:none;stroke:var(--ink);stroke-width:1.2}
.dwg .swing{fill:none;stroke:var(--ink);stroke-width:.6}
.dwg .win{fill:none;stroke:var(--ink);stroke-width:.7}
.dwg .glass{fill:none;stroke:var(--accent);stroke-width:.7}
.dwg .glassline{fill:none;stroke:var(--accent);stroke-width:.9}
.dwg .glassfill{fill:var(--accent);stroke:var(--accent);stroke-width:.4}
.dwg .leaf{fill:var(--sheet);stroke:var(--ink);stroke-width:.8}
.dwg .thin{fill:none;stroke:var(--ink);stroke-width:.7}
.dwg .hidden{fill:none;stroke:var(--ink2);stroke-width:.6;stroke-dasharray:4 3}
.dwg .hiddenrect{fill:none;stroke:var(--furn);stroke-width:.6;stroke-dasharray:4 3}
.dwg .arrow{fill:var(--ink)}
.dwg .rail{fill:none;stroke:var(--ink);stroke-width:1.4}
.dwg .rail2{fill:var(--sheet);stroke:var(--ink);stroke-width:.7}
.dwg .skylight{fill:none;stroke:var(--accent);stroke-width:.9;stroke-dasharray:7 3 1.5 3}
.dwg .dim,.dwg .dimext{fill:none;stroke:var(--ink2);stroke-width:.55}
.dwg .dimtick{fill:none;stroke:var(--ink);stroke-width:1.1}
.dwg .dimtext{fill:var(--ink2);font-family:var(--f-mono)}
.dwg .label{fill:var(--ink);font-weight:600;letter-spacing:.04em}
.dwg .sublabel{fill:var(--ink2);font-family:var(--f-body)}
.dwg .small,.dwg .tiny,.dwg .tiny2{fill:var(--ink2);font-family:var(--f-body)}
.dwg .code{fill:var(--accent);font-family:var(--f-mono);font-weight:500}
.dwg .accenttext{fill:var(--accent);font-weight:600;letter-spacing:.04em}
.dwg .secline{fill:none;stroke:var(--mark);stroke-width:2}
.dwg .secarrow{fill:var(--mark)}
.dwg .secbubble{fill:var(--sheet);stroke:var(--mark);stroke-width:1.2}
.dwg .secletter{fill:var(--mark);font-weight:700}
.dwg .ground{fill:none;stroke:var(--ink);stroke-width:1.6}
.dwg .roof{fill:var(--roof);stroke:var(--ink);stroke-width:.5}
.dwg .elev{fill:none;stroke:var(--ink2);stroke-width:.8}
.dwg .elevlight{fill:none;stroke:var(--furn2);stroke-width:.6}
.dwg .light{fill:none;stroke:var(--sun);stroke-width:1.1;stroke-dasharray:6 4}
.dwg .levelmark{fill:var(--ink)}
.dwg .shadow{fill:var(--shadow)}
.dwg .recess{fill:var(--recess)}
.dwg .wood{fill:var(--wood)}
.dwg .slat{stroke:var(--woodline);stroke-width:1.2}
.dwg .glasspane{fill:var(--glasspane)}
.dwg .frame{fill:none;stroke:var(--ink);stroke-width:.9}
.dwg .glassrail{fill:var(--glassrail);fill-opacity:.55;stroke:var(--ink);stroke-width:.6}
.dwg .reflect{stroke:var(--reflect);stroke-width:1.4;stroke-opacity:.9}
.dwg .plantelev{fill:var(--plant);stroke:var(--gardenline);stroke-width:.6}
.dwg .gate{fill:var(--gate)}
.dwg .slat2{stroke:var(--gateline);stroke-width:1.6}
.dwg .leader{fill:none;stroke:var(--ink2);stroke-width:.6}
.dwg .leaderdot{fill:var(--ink)}
.dwg .note{fill:var(--ink);font-family:var(--f-body)}
.dwg .barfill{fill:var(--ink);stroke:var(--ink);stroke-width:.6}
.dwg .barempty{fill:var(--sheet);stroke:var(--ink);stroke-width:.6}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


def _e(t):
    return html.escape(t)


def tabela_areas(q):
    rows = ['<tr class="grp"><td colspan="2">Térreo</td></tr>']
    rows += [f'<tr><td>{_e(n)}</td><td class="n">{fmt(v)}</td></tr>' for n, v in q["terreo"]]
    rows.append(f'<tr class="sum"><td>Área útil do térreo</td><td class="n">{fmt(q["util_t"])}</td></tr>')
    rows.append('<tr class="grp"><td colspan="2">Pavimento superior</td></tr>')
    rows += [f'<tr><td>{_e(n)}</td><td class="n">{fmt(v)}</td></tr>' for n, v in q["superior"]]
    rows.append(f'<tr class="sum"><td>Área útil do superior</td><td class="n">{fmt(q["util_s"])}</td></tr>')
    rows.append(f'<tr><td>Vazio da escada (não somado)</td><td class="n">{fmt(q["vazio"])}</td></tr>')
    rows.append('<tr class="grp"><td colspan="2">Área construída</td></tr>')
    rows.append(f'<tr><td>Térreo (inclui garagem coberta)</td><td class="n">{fmt(q["terreo_constr"])}</td></tr>')
    rows.append(f'<tr><td>Superior (inclui varanda e vazio)</td><td class="n">{fmt(q["sup_constr"])}</td></tr>')
    rows.append(f'<tr class="total"><td>Total construído</td><td class="n">{fmt(q["total"])} m²</td></tr>')
    rows.append(f'<tr><td>Quintal descoberto</td><td class="n">{fmt(q["quintal"])}</td></tr>')
    return ('<table><thead><tr><th>Ambiente</th><th class="n">m²</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>")


def tabela_esquadrias():
    rows = "".join(f'<tr><td class="mono">{c}</td><td>{_e(t)}</td><td class="n">{d}</td>'
                   f'<td class="n">{pt}</td><td class="n">{n}</td></tr>' for c, t, d, pt, n in ESQUADRIAS)
    return ('<table><thead><tr><th>Cód.</th><th>Tipo</th><th class="n">L × H (m)</th>'
            '<th class="n">Peitoril</th><th class="n">Qtd.</th></tr></thead><tbody>' + rows + "</tbody></table>")


def pagina_html(svgs, q):
    def fig(key, titulo, nota, small=False):
        svg = svgs[key][0]
        if small:
            svg = svg.replace('class="dwg"', 'class="dwg small"', 1)
        return (f'<figure><figcaption><h3>{titulo}</h3><span>{nota}</span></figcaption>'
                f'<div class="scroll" tabindex="0" aria-label="{titulo}">{svg}</div>'
                f'<p class="hint">Arraste para o lado para ver o desenho inteiro →</p></figure>')

    programa = "".join(f'<li><span class="ok">✓ atendido</span><h3>{_e(t)}</h3><p>{_e(x)}</p></li>' for t, x in PROGRAMA)
    partido = "".join(f'<div class="item"><h3>{_e(t)}</h3><p>{_e(x)}</p></div>' for t, x in PARTIDO)
    memorial = "".join(f'<div class="item"><h3>{_e(t)}</h3><p>{_e(x)}</p></div>' for t, x in MEMORIAL)
    verificar = "".join(f'<div class="item"><h3>{_e(t)}</h3><p>{_e(x)}</p></div>' for t, x in VERIFICAR)
    return f"""<title>Sobrado 4×20</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{PAGE_CSS}</style>
<div class="wrap">
  <header class="head">
    <div class="intro">
      <span class="eyebrow">Anteprojeto residencial · lote 4 × 20 m</span>
      <h1>Sobrado 4×20</h1>
      <p class="lede">Casa de dois pavimentos com duas suítes, sala e cozinha integradas, lavabo junto com a
      lavanderia e garagem coberta de 5,50 m ocupando toda a frente do lote.</p>
    </div>
    <dl class="carimbo">
      <div><dt>Lote</dt><dd>4,00 × 20,00 m</dd></div>
      <div><dt>Área do lote</dt><dd>{fmt(q['lote'])} m²</dd></div>
      <div><dt>Área construída</dt><dd>{fmt(q['total'])} m²</dd></div>
      <div><dt>Pavimentos</dt><dd>2 (térreo + superior)</dd></div>
      <div><dt>Quartos</dt><dd>2 suítes</dd></div>
      <div><dt>Altura total</dt><dd>6,60 m</dd></div>
      <div class="full"><dt>Fase</dt><dd>Estudo preliminar · novembro de 2026</dd></div>
    </dl>
  </header>

  <section aria-labelledby="h-prog">
    <h2 id="h-prog">Programa pedido</h2>
    <ol class="programa">{programa}</ol>
  </section>

  <section aria-labelledby="h-des">
    <h2 id="h-des">Desenhos</h2>
    <div class="legend">
      <span><i class="lg-wall"></i>parede cortada</span>
      <span><i class="lg-glass"></i>vidro / esquadria</span>
      <span><i class="lg-proj"></i>projeção (acima ou abaixo)</span>
      <span><i class="lg-sec"></i>linha de corte AA</span>
      <span><i class="lg-sun"></i>luz da claraboia</span>
    </div>
    <div class="set">
      {fig("planta-terreo", "Planta do térreo", "rua à esquerda · cotas em metros")}
      {fig("planta-superior", "Planta do pavimento superior", "alinhada com o térreo")}
      {fig("corte-aa", "Corte AA", "longitudinal, pela escada")}
    </div>
  </section>

  <section class="duo" aria-label="Fachada e quadro de áreas">
    {fig("fachada-frontal", "Fachada frontal", "vista da rua", small=True)}
    <div class="tablebox">
      <h3 style="padding:10px 0 4px;text-transform:uppercase;letter-spacing:.05em">Quadro de áreas</h3>
      {tabela_areas(q)}
      <div class="indices">
        <div><b>{fmt(q['to'] * 100, 1)}%</b><small>taxa de ocupação</small></div>
        <div><b>{fmt(q['ca'])}</b><small>coef. de aproveitamento</small></div>
        <div><b>até {fmt(q['perm'] * 100, 1)}%</b><small>área permeável</small></div>
      </div>
    </div>
  </section>

  <section aria-labelledby="h-part">
    <h2 id="h-part">Como a casa foi resolvida</h2>
    <div class="cols">{partido}</div>
  </section>

  <section aria-labelledby="h-esq">
    <h2 id="h-esq">Quadro de esquadrias</h2>
    <div class="tablebox"><div class="scroll">{tabela_esquadrias()}</div></div>
  </section>

  <section aria-labelledby="h-mem">
    <h2 id="h-mem">Memorial resumido</h2>
    <div class="cols">{memorial}</div>
  </section>

  <section class="aviso" aria-labelledby="h-ver">
    <h2 id="h-ver">Antes de construir, verifique</h2>
    <div class="cols">{verificar}</div>
  </section>

  <footer class="files">
    <h3>Arquivos no repositório</h3>
    <p><code>projeto/prancha-a3.pdf</code> prancha única em A3, escala 1:100, para imprimir e levar ao arquiteto ou engenheiro.</p>
    <p><code>projeto/sobrado-4x20.dxf</code> plantas, corte e fachada para AutoCAD, em metros e separados por camadas.</p>
    <p><code>gerar_projeto.py</code> modelo paramétrico que gera todos os desenhos e o quadro de áreas.</p>
  </footer>
</div>
"""


# --------------------------------------------------------------------------
# Prancha A3 (1:100) para PDF
# --------------------------------------------------------------------------
def prancha_html(S, q):
    def svg_mm(key, d_kw):
        sa, T = d_kw
        w_mm = T.W / S * 10.0     # 1:100 -> 1 m = 10 mm
        h_mm = T.H / S * 10.0
        sa = sa.replace(f'width="{T.W:.0f}" height="{T.H:.0f}"', f'width="{w_mm:.2f}mm" height="{h_mm:.2f}mm"', 1)
        return sa

    blocks = {}
    for key, d in DRAWINGS.items():
        kw = {"xrange": XR} if key != "fachada-frontal" else {"extra": (0, 0, 4.3, 0)}
        blocks[key] = svg_mm(key, to_svg(d, s=S, uid="p" + key, standalone=True, **kw))

    areas_rows = "".join(f"<tr><td>{_e(n)}</td><td class='n'>{fmt(v)}</td></tr>" for n, v in q["terreo"] + q["superior"])
    esq_rows = "".join(f"<tr><td>{c}</td><td>{_e(t.split(' (')[0])}</td><td class='n'>{d}</td><td class='n'>{pt}</td>"
                       f"<td class='n'>{n}</td></tr>" for c, t, d, pt, n in ESQUADRIAS)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS}">
<style>
@page{{size:420mm 297mm;margin:0}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Source Sans 3',Arial,sans-serif;color:#1b1f23;background:#fff}}
.sheet{{width:420mm;height:297mm;padding:9mm 10mm;position:relative;display:grid;
  grid-template-columns:257mm 1fr;gap:0 7mm;border:0}}
.frame{{position:absolute;inset:6mm;border:.5mm solid #1b1f23;pointer-events:none}}
.col{{display:flex;flex-direction:column;gap:1.2mm;min-width:0}}
h4{{font-family:'Barlow Condensed',Arial Narrow,sans-serif;font-size:10pt;letter-spacing:.06em;margin:1.2mm 0 0;
  text-transform:uppercase;display:flex;justify-content:space-between;align-items:baseline}}
h4 span{{font-family:'IBM Plex Mono',monospace;font-size:6.5pt;font-weight:400;letter-spacing:0;text-transform:none;color:#4a535b}}
svg{{display:block}}
table{{border-collapse:collapse;width:100%;font-size:6.6pt;line-height:1.25}}
td,th{{padding:.45mm 1mm;border-bottom:.15mm solid #c6ccc8;text-align:left}}
th{{font-family:'IBM Plex Mono',monospace;font-weight:500;font-size:5.6pt;text-transform:uppercase;color:#4a535b}}
.n{{text-align:right;font-family:'IBM Plex Mono',monospace;white-space:nowrap}}
.tot td{{font-weight:700;border-top:.3mm solid #1b1f23;border-bottom:.3mm solid #1b1f23}}
.carimbo{{margin-top:auto;border:.35mm solid #1b1f23;display:grid;grid-template-columns:1fr 1fr;font-size:6.6pt}}
.carimbo div{{padding:1mm 1.6mm;border-bottom:.15mm solid #9aa1a8;border-right:.15mm solid #9aa1a8}}
.carimbo div:nth-child(2n){{border-right:0}}
.carimbo .full{{grid-column:1/-1;border-right:0}}
.carimbo b{{display:block;font-family:'Barlow Condensed',Arial Narrow,sans-serif;font-size:10pt}}
.carimbo .t b{{font-size:15pt;letter-spacing:.02em}}
.carimbo small{{font-family:'IBM Plex Mono',monospace;font-size:5.4pt;text-transform:uppercase;color:#4a535b}}
.obs{{font-size:5.8pt;color:#4a535b;line-height:1.3}}
</style></head><body><div class="sheet"><div class="frame"></div>
<div class="col">
  <h4>Planta do térreo <span>esc. 1:100</span></h4>{blocks['planta-terreo']}
  <h4>Planta do pavimento superior <span>esc. 1:100</span></h4>{blocks['planta-superior']}
  <h4>Corte AA <span>esc. 1:100</span></h4>{blocks['corte-aa']}
</div>
<div class="col">
  <h4>Fachada frontal <span>esc. 1:100</span></h4>{blocks['fachada-frontal']}
  <h4>Quadro de áreas (m²)</h4>
  <table>{areas_rows}
    <tr><td>Quintal descoberto</td><td class='n'>{fmt(q['quintal'])}</td></tr>
    <tr class="tot"><td>Área construída total (térreo {fmt(q['terreo_constr'])} + superior {fmt(q['sup_constr'])})</td><td class='n'>{fmt(q['total'])}</td></tr>
    <tr><td>Taxa de ocupação · Coef. aproveitamento · Permeável</td><td class='n'>{fmt(q['to']*100,1)}% · {fmt(q['ca'])} · {fmt(q['perm']*100,1)}%</td></tr>
  </table>
  <h4>Quadro de esquadrias</h4>
  <table><tr><th>Cód.</th><th>Tipo</th><th class="n">L × H</th><th class="n">Peit.</th><th class="n">Qtd</th></tr>{esq_rows}</table>
  <p class="obs">Escada: 16 espelhos de 18 cm, pisos de 28 cm, largura 0,90 m, guarda-corpo h = 1,10 m. Pé-direito 2,70 m.
  Paredes laterais cegas (Código Civil, art. 1.301). Banheiros do superior com exaustão mecânica até a cobertura.
  Verificar recuos e índices no código de obras e no zoneamento do município.</p>
  <div class="carimbo">
    <div class="full t"><small>Projeto</small><b>Sobrado 4×20 — anteprojeto</b></div>
    <div><small>Lote</small><b>4,00 × 20,00 m ({fmt(q['lote'])} m²)</b></div>
    <div><small>Área construída</small><b>{fmt(q['total'])} m²</b></div>
    <div><small>Escala</small><b>1:100 (A3)</b></div>
    <div><small>Data</small><b>nov/2026</b></div>
    <div class="full"><small>Observação</small><b style="font-size:7.5pt;font-family:'Source Sans 3',Arial,sans-serif;font-weight:400">
    Estudo preliminar. Não substitui o projeto legal assinado por responsável técnico (RRT/ART).</b></div>
  </div>
</div>
</div></body></html>"""


PDF_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const [src, out] = process.argv.slice(1);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + src, { waitUntil: 'networkidle' });
  await p.pdf({ path: out, width: '420mm', height: '297mm', printBackground: true });
  await b.close();
})();
"""


def gerar_pdf(html_path, pdf_path):
    try:
        r = subprocess.run(["node", "-e", PDF_JS, html_path, pdf_path], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print("PDF não gerado (precisa de node + playwright):", r.stderr.strip()[:300])
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("PDF não gerado:", exc)
        return False


# --------------------------------------------------------------------------
# README
# --------------------------------------------------------------------------
def readme_md(q):
    linhas = ["# Sobrado 4×20 — anteprojeto", "",
              "Casa de dois pavimentos para um lote de **4,00 × 20,00 m**: duas suítes, sala e cozinha integradas, "
              "lavabo junto com a lavanderia e garagem coberta de **5,50 m** ocupando toda a frente do terreno.", "",
              f"**Área construída:** {fmt(q['total'])} m² · **Lote:** {fmt(q['lote'])} m² · "
              f"**Taxa de ocupação:** {fmt(q['to'] * 100, 1)}% · **Coef. de aproveitamento:** {fmt(q['ca'])} · "
              f"**Área permeável:** até {fmt(q['perm'] * 100, 1)}%", "",
              "## Programa pedido", ""]
    for t, x in PROGRAMA:
        linhas.append(f"- **{t}** — {x}")
    linhas += ["", "## Desenhos", "",
               "As plantas estão com a rua à esquerda; plantas e corte usam a mesma escala e o mesmo eixo de "
               "profundidade, então podem ser lidos alinhados.", "",
               "### Planta do térreo", "", "![Planta do térreo](projeto/planta-terreo.svg)", "",
               "### Planta do pavimento superior", "", "![Planta do pavimento superior](projeto/planta-superior.svg)", "",
               "### Corte AA", "", "![Corte AA](projeto/corte-aa.svg)", "",
               "### Fachada frontal", "", "![Fachada frontal](projeto/fachada-frontal.svg)", "",
               "## Quadro de áreas", "", "| Ambiente | m² |", "|---|---:|"]
    for n, v in q["terreo"]:
        linhas.append(f"| Térreo — {n} | {fmt(v)} |")
    for n, v in q["superior"]:
        linhas.append(f"| Superior — {n} | {fmt(v)} |")
    linhas += [f"| Quintal descoberto | {fmt(q['quintal'])} |",
               f"| Área útil (térreo + superior) | {fmt(q['util_t'] + q['util_s'])} |",
               f"| **Área construída** (térreo {fmt(q['terreo_constr'])} + superior {fmt(q['sup_constr'])}) | **{fmt(q['total'])}** |",
               "", "## Como a casa foi resolvida", ""]
    for t, x in PARTIDO:
        linhas.append(f"- **{t}.** {x}")
    linhas += ["", "## Quadro de esquadrias", "", "| Cód. | Tipo | L × H (m) | Peitoril | Qtd. |", "|---|---|---:|---:|---:|"]
    for c, t, d, pt, n in ESQUADRIAS:
        linhas.append(f"| {c} | {t} | {d} | {pt} | {n} |")
    linhas += ["", "## Memorial resumido", ""]
    for t, x in MEMORIAL:
        linhas.append(f"- **{t}.** {x}")
    linhas += ["", "## Antes de construir, verifique", ""]
    for t, x in VERIFICAR:
        linhas.append(f"- **{t}.** {x}")
    linhas += ["", "## Arquivos", "",
               "| Arquivo | Conteúdo |", "|---|---|",
               "| `projeto/prancha-a3.pdf` | Prancha única A3 em escala 1:100 (plantas, corte, fachada, quadros) |",
               "| `projeto/sobrado-4x20.dxf` | Desenhos para CAD, em metros, separados por camadas |",
               "| `projeto/*.svg` | Desenhos em vetor |",
               "| `projeto/index.html` | Página de apresentação (tema claro e escuro) |",
               "| `gerar_projeto.py` | Modelo paramétrico que gera todos os arquivos acima |",
               "", "Para alterar o projeto, edite as coordenadas em `gerar_projeto.py` e rode:", "",
               "```bash", "pip install shapely ezdxf", "python3 gerar_projeto.py   # o PDF usa node + playwright, se houver",
               "```", ""]
    return "\n".join(linhas)


DRAWINGS = {}
XR = (-2.75, 22.75)


def main():
    global DRAWINGS
    os.makedirs(OUT, exist_ok=True)
    DRAWINGS = {"planta-terreo": planta_terreo(), "planta-superior": planta_superior(),
                "corte-aa": corte_aa(), "fachada-frontal": fachada()}
    S = 56
    svgs = {}
    for key, d in DRAWINGS.items():
        kw = {"xrange": XR} if key != "fachada-frontal" else {"extra": (0, 0, 4.3, 0)}
        sa, _ = to_svg(d, s=S, uid=key, standalone=True, **kw)
        with open(os.path.join(OUT, f"{key}.svg"), "w", encoding="utf-8") as f:
            f.write(sa)
        svgs[key] = to_svg(d, s=S, uid=key, standalone=False, **kw)

    to_dxf([(DRAWINGS["planta-terreo"], (0, 0), "PLANTA DO TÉRREO"),
            (DRAWINGS["planta-superior"], (0, -9), "PLANTA DO PAVIMENTO SUPERIOR"),
            (DRAWINGS["corte-aa"], (0, -26), "CORTE AA"),
            (DRAWINGS["fachada-frontal"], (27, -26), "FACHADA FRONTAL")],
           os.path.join(OUT, "sobrado-4x20.dxf"))

    q = quadro()
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina_html(svgs, q))
    prancha = os.path.join(OUT, "prancha-a3.html")
    with open(prancha, "w", encoding="utf-8") as f:
        f.write(prancha_html(S, q))
    ok = gerar_pdf(prancha, os.path.join(OUT, "prancha-a3.pdf"))
    with open(os.path.join(RAIZ, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_md(q))

    print(f"Área construída: {fmt(q['total'])} m² | útil: {fmt(q['util_t'] + q['util_s'])} m² | "
          f"TO {fmt(q['to'] * 100, 1)}% | CA {fmt(q['ca'])} | permeável até {fmt(q['perm'] * 100, 1)}%")
    print("Arquivos em", OUT, "(PDF ok)" if ok else "(sem PDF)")


if __name__ == "__main__":
    main()
