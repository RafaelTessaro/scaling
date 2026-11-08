#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anteprojeto "Casa Térrea 4x20" - gerador dos desenhos.

Um único modelo geométrico (em metros) alimenta todos os produtos:
planta baixa, planta de cobertura, corte, fachada, quadros, SVG, DXF,
página HTML, prancha A3 em PDF e README. Para alterar o projeto, mude
as coordenadas aqui e rode de novo:

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

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

RAIZ = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(RAIZ, "projeto")

# --------------------------------------------------------------------------
# Parâmetros gerais
# --------------------------------------------------------------------------
LOTE_W, LOTE_L = 4.00, 20.00
GARAGEM_L = 5.50          # comprimento da garagem (exigência do programa)

# faixas da largura
XA0, XA1 = 0.15, 1.00     # corredor (0,85 m)
XB0, XB1 = 1.10, 3.85     # faixa dos cômodos (2,75 m)
XBAN = (2.40, 2.50)       # parede entre os dois banheiros

# cadeia da profundidade (ver checagem no README)
Y_FRENTE = (5.50, 5.65)
Y_SALA = (5.65, 10.35)
Y_LAV = (10.45, 11.85)
Y_Q1 = (11.95, 14.80)
Y_BAN = (14.90, 17.10)
Y_Q2 = (17.20, 19.85)
Y_FUNDO = (19.85, 20.00)

# Níveis
Z_CALCADA = 0.00
Z_GARAGEM = 0.05
Z_PISO = 0.15
PE_DIREITO = 2.70
Z_FORRO = round(Z_PISO + PE_DIREITO, 2)     # 2,85
Z_COB = 3.10              # cobertura plana (telha) / base das janelas dos sheds
Z_VIDRO_TOPO = 3.90       # topo do vidro dos sheds
Z_SHED = 4.05             # topo dos sheds
Z_PLATIBANDA = 3.50
Z_MURO = 2.80             # muros da garagem e pergolado
Z_PORTAO = 2.20

# Sheds: (nome, y do vidro, y do ponto baixo, x0 do vidro, x1 do vidro)
SHEDS = [
    ("shed 1", 7.90, Y_SALA[1], 0.75, 3.25),   # sala + cozinha
    ("shed 2", 11.90, Y_Q1[1], 1.25, 3.25),    # suíte 1
    ("shed 3", 17.15, Y_Q2[1], 0.75, 3.25),    # suíte 2
]
# Domus ventilados: (centro x, centro y, lado)
DOMUS = [(2.10, 11.15, 0.80), (1.75, 16.68, 0.60), (3.18, 15.33, 0.60),
         (0.575, 11.15, 0.50), (0.575, 16.00, 0.50)]

CORTE_X = 2.00            # posição do corte AA


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

    def finalize(self):
        holes = unary_union(self.cuts) if self.cuts else None
        for geoms, cls in ((self.walls, "wall"), (self.muros, "muro")):
            if geoms:
                g = unary_union(geoms)
                if holes is not None:
                    g = g.difference(holes)
                self.area(g, cls, layer=2)

    def label(self, p, nome, *linhas, size=0.24, sub=0.18):
        """Rótulo de ambiente: nome + linhas secundárias, empilhados para baixo na tela."""
        dx, dy = self.down
        alturas = [size * 1.25] + [sub * 1.3] * len(linhas)
        off = -sum(alturas) / 2 + alturas[0] / 2
        self.text((p[0] + dx * off, p[1] + dy * off), nome, size=size, cls="label")
        acc = off + alturas[0] / 2
        for i, ln in enumerate(linhas):
            acc += alturas[i + 1] / 2
            self.text((p[0] + dx * acc, p[1] + dy * acc), ln, size=sub, cls="sublabel")
            acc += alturas[i + 1] / 2


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


def dim_chain(d, axis, pos, vals, ext=None, label_min=0.40, toff=None, size=0.17, labels=None):
    """Cadeia de cotas. axis=1 varia na 2ª coordenada (1ª fixa em pos); axis=0 o contrário."""
    def P(v, w):
        return (w, v) if axis == 1 else (v, w)

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
        lab = labels[i] if labels else fmt(L)
        if L < label_min or lab is None:
            continue
        d.text(P((vals[i] + vals[i + 1]) / 2, pos + toff), lab, size=size, cls="dimtext", rot=rot, layer=4)


def scale_bar(d, p, comp=2):
    """Escala gráfica de 0 a `comp` metros, na horizontal da tela."""
    if d.plano:
        def P(t, o=0.0):
            return (p[0] + o, p[1] + t)
        up = -1
    else:
        def P(t, o=0.0):
            return (p[0] + t, p[1] + o)
        up = 1
    for i in range(comp):
        cls = "barfill" if i % 2 == 0 else "barempty"
        d.poly([P(i, 0), P(i + 1, 0), P(i + 1, up * 0.07), P(i, up * 0.07)], cls, layer=4)
    for i in range(comp + 1):
        d.text(P(i, up * 0.22), str(i), size=0.13, cls="dimtext", layer=5)
    d.text(P(comp + 0.25, up * 0.04), "m", size=0.13, cls="dimtext", layer=5)


def section_marks(d, ys):
    """Indicação do corte AA na planta (a seta aponta no sentido da vista: +x)."""
    for y in ys:
        d.line([(CORTE_X, y - 0.35), (CORTE_X, y + 0.35)], "secline", layer=4)
        d.poly([(CORTE_X, y - 0.10), (CORTE_X, y + 0.10), (CORTE_X + 0.30, y)], "secarrow", layer=4)
        d.circle((CORTE_X - 0.42, y), 0.20, "secbubble", layer=4)
        d.text((CORTE_X - 0.42, y), "A", size=0.20, cls="secletter", layer=5)


# --------------------------------------------------------------------------
# Mobiliário (referência de escala)
# --------------------------------------------------------------------------
def bed_head_x1(d, x0, y0, x1, y1):
    d.rect(x0, y0, x1, y1)
    w = y1 - y0
    d.rect(x1 - 0.46, y0 + 0.08, x1 - 0.12, y0 + w / 2 - 0.04)
    d.rect(x1 - 0.46, y0 + w / 2 + 0.04, x1 - 0.12, y1 - 0.08)
    d.line([(x1 - 0.60, y0), (x1 - 0.60, y1)], "furn", layer=1)
    d.line([(x1 - 0.60, y1), (x1 - 0.92, y1 - 0.32)], "furn", layer=1)
    d.line([(x1 - 0.92, y1 - 0.32), (x1 - 0.60, y1 - 0.32)], "furn", layer=1)


def wardrobe_v(d, x0, y0, x1, y1):
    """Armário encostado em parede paralela ao eixo y."""
    d.rect(x0, y0, x1, y1)
    xm = (x0 + x1) / 2
    d.line([(xm, y0), (xm, y1)], "furn", layer=1)
    n = max(2, int((y1 - y0) / 0.30))
    for i in range(1, n):
        y = y0 + i * (y1 - y0) / n
        d.line([(xm - 0.12, y - 0.06), (xm + 0.12, y + 0.06)], "furnlight", layer=1)


def wardrobe_h(d, x0, y0, x1, y1):
    """Armário encostado em parede paralela ao eixo x."""
    d.rect(x0, y0, x1, y1)
    ym = (y0 + y1) / 2
    d.line([(x0, ym), (x1, ym)], "furn", layer=1)
    n = max(2, int((x1 - x0) / 0.30))
    for i in range(1, n):
        x = x0 + i * (x1 - x0) / n
        d.line([(x - 0.06, ym - 0.12), (x + 0.06, ym + 0.12)], "furnlight", layer=1)


def toilet(d, xw, yc, s=1):
    """Vaso sanitário com a caixa encostada na parede x = xw, voltado para +x (s=1) ou -x (s=-1)."""
    d.rect(xw, yc - 0.20, xw + s * 0.18, yc + 0.20)
    d.poly(ellipse_pts(xw + s * 0.42, yc, 0.24, 0.18))


def basin(d, x0, y0, x1, y1, rx=0.15, ry=0.12):
    d.rect(x0, y0, x1, y1)
    d.poly(ellipse_pts((x0 + x1) / 2, (y0 + y1) / 2, rx, ry))


def shower(d, x0, y0, x1, y1, glass_at):
    d.rect(x0, y0, x1, y1, "wet", layer=0)
    d.circle(((x0 + x1) / 2, (y0 + y1) / 2), 0.05)
    y = y0 if glass_at == "y0" else y1
    d.line([(x0, y), (x1, y)], "glassline", layer=3)


# --------------------------------------------------------------------------
# Áreas
# --------------------------------------------------------------------------
def areas():
    return {
        "GARAGEM": box(0.15, 0.0, 3.85, GARAGEM_L).area,
        "SALA + COZINHA": box(0.15, Y_SALA[0], 3.85, Y_SALA[1]).area,
        "LAVABO + LAVANDERIA": box(XB0, Y_LAV[0], XB1, Y_LAV[1]).area,
        "CIRCULAÇÃO": box(XA0, Y_SALA[1], XA1, Y_BAN[1]).area,
        "SUÍTE 1": box(XB0, Y_Q1[0], XB1, Y_Q1[1]).area,
        "BANHO 1": box(XB0, Y_BAN[0], XBAN[0], Y_BAN[1]).area,
        "BANHO 2": box(XBAN[1], Y_BAN[0], XB1, Y_BAN[1]).area,
        "SUÍTE 2": box(0.15, Y_Q2[0], 3.85, Y_Q2[1]).area,
    }


# --------------------------------------------------------------------------
# PLANTA BAIXA
# --------------------------------------------------------------------------
def planta_baixa():
    d = Drawing("planta")
    a = areas()

    # pisos
    d.area(box(-0.6, -1.50, 4.6, 0.0), "sidewalk")
    d.line([(-0.6, -1.50), (4.6, -1.50)], "elevlight", layer=3)
    d.area(box(0.15, 0.0, 3.85, GARAGEM_L), "grasspave")
    d.area(box(XB0, Y_LAV[0], XB1, Y_LAV[1]), "floor-wet")
    d.area(box(XB0, Y_BAN[0], XB1, Y_BAN[1]), "floor-wet")

    # muros da garagem (aberta, com pergolado) e paredes da casa
    d.muro(0.00, 0.00, 0.15, GARAGEM_L)
    d.muro(3.85, 0.00, 4.00, GARAGEM_L)
    d.wall(1.05, 0.00, 1.15, 0.15)                        # pilar entre portões
    d.wall(0.00, GARAGEM_L, 0.15, LOTE_L)                 # divisa esquerda
    d.wall(3.85, GARAGEM_L, 4.00, LOTE_L)                 # divisa direita
    d.wall(0.15, *Y_FRENTE[:1], 3.85, Y_FRENTE[1])        # fachada
    d.wall(XB0, Y_SALA[1], XB1, Y_LAV[0])                 # sala | lavabo
    d.wall(XA1, Y_SALA[1], XB0, Y_BAN[1] + 0.10)          # corredor | cômodos
    d.wall(XB0, Y_LAV[1], XB1, Y_Q1[0])                   # lavabo | suíte 1
    d.wall(XB0, Y_Q1[1], XB1, Y_BAN[0])                   # suíte 1 | banhos
    d.wall(XBAN[0], Y_BAN[0], XBAN[1], Y_BAN[1])          # banho 1 | banho 2
    d.wall(0.15, Y_BAN[1], 3.85, Y_Q2[0])                 # banhos/corredor | suíte 2
    d.wall(0.15, Y_FUNDO[0], 3.85, Y_FUNDO[1])            # fundo (na divisa)

    # esquadrias
    door_h(d, 0.20, 1.10, *Y_FRENTE, "x0", +1)            # P1 entrada
    window_h(d, 1.60, 3.10, *Y_FRENTE)                    # J1 sala -> garagem
    door_v(d, 10.55, 11.25, XA1, XB0, "y0", +1)           # P2 lavabo + lavanderia
    door_v(d, 12.05, 12.85, XA1, XB0, "y0", +1)           # P3 suíte 1
    door_h(d, 1.20, 1.80, Y_Q1[1], Y_BAN[0], "x0", +1)    # P4 banho 1
    door_h(d, 0.17, 0.97, Y_BAN[1], Y_Q2[0], "x0", +1)    # P3 suíte 2
    door_h(d, 2.60, 3.20, Y_BAN[1], Y_Q2[0], "x0", -1)    # P4 banho 2

    # portões no alinhamento
    door(d, (0.15, 0.05), (1.05, 0.05), (0.15, 0.95))     # portão social 0,90
    d.line([(0.15, 0.05), (1.05, 0.05)], "hidden")
    d.rect(1.15, 0.00, 3.85, 0.05, "leaf", layer=3)       # portão basculante 2,70
    d.rect(1.15, 0.05, 3.85, 1.15, "hiddenrect", layer=3)

    # pergolado (projeção)
    for i in range(11):
        y = 0.40 + i * 0.50
        d.line([(0.15, y), (3.85, y)], "pergola", layer=1)

    # projeções da cobertura: janelas dos sheds e domus
    for nome, yv, ye, x0, x1 in SHEDS:
        d.line([(x0, yv), (x1, yv)], "skylight", layer=3)
    for cx, cy, s in DOMUS:
        h = s / 2
        d.rect(cx - h, cy - h, cx + h, cy + h, "skylightbox", layer=3)
        d.line([(cx - h, cy - h), (cx + h, cy + h)], "skylightbox", layer=3)
        d.line([(cx - h, cy + h), (cx + h, cy - h)], "skylightbox", layer=3)

    # mobiliário ----------------------------------------------------------
    # carro 1,80 x 4,50 (à direita) e passagem à esquerda
    d.poly(rounded_rect(1.80, 0.45, 3.60, 4.95, 0.30), "car")
    d.poly([(1.93, 3.60), (3.47, 3.60), (3.36, 3.10), (2.04, 3.10)], "car")
    d.poly([(2.00, 1.10), (3.40, 1.10), (3.33, 1.45), (2.07, 1.45)], "car")
    # estar
    sx0, sy0, sx1, sy1 = 2.95, 5.80, 3.85, 7.25
    d.rect(sx0, sy0, sx1, sy1)
    d.rect(sx1 - 0.22, sy0, sx1, sy1)
    d.rect(sx0, sy0, sx1 - 0.22, sy0 + 0.20)
    d.rect(sx0, sy1 - 0.20, sx1 - 0.22, sy1)
    d.line([(sx0, (sy0 + sy1) / 2), (sx1 - 0.22, (sy0 + sy1) / 2)], "furn", layer=1)
    d.rect(0.15, 6.65, 0.50, 7.65)                         # rack
    d.rect(0.20, 6.75, 0.26, 7.55)                         # TV
    # jantar (mesa 1,20 x 0,80 + 4 cadeiras)
    d.rect(1.50, 7.80, 2.70, 8.60)
    for xc in (1.85, 2.35):
        d.rect(xc - 0.20, 7.35, xc + 0.20, 7.75)
        d.rect(xc - 0.20, 8.65, xc + 0.20, 9.05)
    # cozinha linear na parede do fundo da sala
    d.rect(XB0, 9.75, XB1, Y_SALA[1])
    d.rect(1.13, 9.68, 1.83, Y_SALA[1])                   # geladeira
    d.line([(1.13, 9.68), (1.83, Y_SALA[1])], "furnlight", layer=1)
    d.poly(rounded_rect(2.15, 9.82, 2.85, 10.28, 0.06))   # cuba
    d.circle((2.50, 10.22), 0.03)
    d.rect(3.10, 9.80, 3.70, 10.30)                        # cooktop
    for cx, cy in ((3.24, 9.93), (3.56, 9.93), (3.24, 10.17), (3.56, 10.17)):
        d.circle((cx, cy), 0.08)
    # lavabo + lavanderia
    d.rect(1.95, 11.25, 2.55, Y_LAV[1])                   # máquina
    d.circle((2.25, 11.55), 0.22)
    d.rect(2.60, 11.33, 3.10, Y_LAV[1])                   # tanque
    d.rect(2.67, 11.40, 3.03, 11.75)
    toilet(d, 3.85, 11.05, s=-1)
    basin(d, 3.35, Y_LAV[0], 3.80, 10.78)
    # suíte 1 (cama de casal 1,38 x 1,88)
    wardrobe_h(d, 1.95, Y_Q1[0], 3.85, 12.50)
    bed_head_x1(d, 1.97, 12.95, 3.85, 14.33)
    d.rect(3.42, 14.36, 3.85, 14.78)
    # banho 1
    basin(d, 2.05, 15.00, XBAN[0], 15.45, rx=0.12, ry=0.17)
    toilet(d, XBAN[0], 15.85, s=-1)
    shower(d, XB0, 16.25, XBAN[0], Y_BAN[1], "y0")
    # banho 2
    shower(d, XBAN[1], Y_BAN[0], XB1, 15.75, "y1")
    toilet(d, XB1, 16.05, s=-1)
    basin(d, 3.50, 16.55, XB1, 17.00, rx=0.12, ry=0.17)
    # suíte 2
    wardrobe_v(d, 0.15, 18.05, 0.70, Y_Q2[1])
    bed_head_x1(d, 1.97, 18.05, 3.85, 19.43)
    d.rect(3.42, 19.45, 3.85, Y_Q2[1])

    # rótulos
    d.label((0.92, 2.70), "GARAGEM", f"{fmt(a['GARAGEM'])} m²", "4,00 × 5,50", size=0.22, sub=0.16)
    d.text((0.92, 4.30), "pergolado + piso drenante", size=0.12, cls="tiny2")
    d.label((2.05, 6.52), "SALA + COZINHA", f"{fmt(a['SALA + COZINHA'])} m²", "integradas", size=0.17, sub=0.14)
    d.text((2.40, 9.40), "cozinha", size=0.14, cls="tiny2")
    d.text((2.45, 10.93), "LAVABO +", size=0.12, cls="label")
    d.text((2.62, 10.93), "LAVANDERIA", size=0.12, cls="label")
    d.text((2.79, 10.93), f"{fmt(a['LAVABO + LAVANDERIA'])} m²", size=0.11, cls="sublabel")
    d.label((1.53, 13.60), "SUÍTE 1", f"{fmt(a['SUÍTE 1'])} m²", "2,75 × 2,85", size=0.20, sub=0.14)
    d.label((1.42, 15.88), "BANHO 1", f"{fmt(a['BANHO 1'])} m²", size=0.13, sub=0.11)
    d.label((2.85, 16.12), "BANHO 2", f"{fmt(a['BANHO 2'])} m²", size=0.13, sub=0.11)
    d.label((1.35, 18.95), "SUÍTE 2", f"{fmt(a['SUÍTE 2'])} m²", "3,70 × 2,65", size=0.22, sub=0.16)
    d.label((0.575, 13.85), "CIRCULAÇÃO", f"{fmt(a['CIRCULAÇÃO'])} m²", size=0.14, sub=0.12)
    d.text((2.0, -1.05), "CALÇADA", size=0.15, cls="tiny2", rot=-90)
    d.text((2.4, -2.05), "RUA", size=0.20, cls="sublabel", rot=-90)
    d.text((0.60, -0.32), "social 0,90", size=0.12, cls="tiny", rot=-90)
    d.text((2.50, -0.32), "portão basculante 2,70", size=0.12, cls="tiny", rot=-90)

    # códigos das esquadrias  (x, y)
    for p, s in (((0.65, 5.30), "P1"), ((2.35, 5.30), "J1"), ((1.20, 10.30), "P2"), ((1.20, 12.00), "P3"),
                 ((1.50, 14.62), "P4"), ((0.57, 17.40), "P3"), ((2.90, 17.40), "P4")):
        d.text(p, s, size=0.11, cls="code")

    # cotas
    dim_chain(d, 1, 4.45, [0, GARAGEM_L, LOTE_L], ext=4.0, labels=["5,50 garagem", "14,50 casa"])
    dim_chain(d, 1, 4.95, [0, LOTE_L], ext=4.0, labels=["20,00 (profundidade do lote)"])
    dim_chain(d, 1, -0.40, [5.50, 5.65, 10.35, 10.45, 11.85, 11.95, 14.80, 14.90, 17.10, 17.20, 19.85, 20.0], ext=0.0)
    dim_chain(d, 0, 20.45, [0, 0.15, XA1, XB0, XBAN[0], XBAN[1], 3.85, 4.0], ext=20.0, label_min=0.5)
    dim_chain(d, 0, 20.95, [0, 4.0], ext=20.0)
    section_marks(d, ys=(-2.15, 21.70))
    scale_bar(d, (4.85, -2.45))
    d.finalize()
    return d


# --------------------------------------------------------------------------
# PLANTA DE COBERTURA
# --------------------------------------------------------------------------
def slope_arrow(d, x, y0, y1, txt):
    d.line([(x, y0), (x, y1)], "slope", layer=4)
    s = 1 if y1 > y0 else -1
    d.poly([(x - 0.06, y1 - s * 0.16), (x + 0.06, y1 - s * 0.16), (x, y1)], "slopehead", layer=4)
    d.text((x - 0.14, (y0 + y1) / 2), txt, size=0.12, cls="tiny2", layer=5)


def planta_cobertura():
    d = Drawing("cobertura")
    d.area(box(-0.6, -1.50, 4.6, 0.0), "sidewalk")
    d.rect(0.0, 0.0, LOTE_W, LOTE_L, "ghost", layer=0)

    # garagem: piso visto entre as vigas do pergolado
    d.area(box(0.15, 0.0, 3.85, GARAGEM_L), "grasspave")
    d.muro(0.00, 0.00, 0.15, GARAGEM_L)
    d.muro(3.85, 0.00, 4.00, GARAGEM_L)
    d.rect(0.15, 0.0, 3.85, 0.15, "pergbeam", layer=2)
    for i in range(11):
        y = 0.40 + i * 0.50
        d.rect(0.15, y - 0.03, 3.85, y + 0.03, "pergbeam", layer=2)

    # telhados
    planos = [(Y_FRENTE[1], SHEDS[0][1], -1), (Y_SALA[1], SHEDS[1][1], -1), (Y_Q1[1], SHEDS[2][1], -1)]
    for y0, y1, _ in planos:
        d.area(box(0.15, y0, 3.85, y1), "roofflat")
    for nome, yv, ye, x0, x1 in SHEDS:
        d.area(box(0.15, yv, 3.85, ye), "roofshed")
        n = int((ye - yv) / 0.25)
        for i in range(1, n):
            y = yv + i * (ye - yv) / n
            d.line([(0.15, y), (3.85, y)], "roofline", layer=1)
        d.rect(0.15, yv - 0.04, 3.85, yv + 0.04, "shededge", layer=3)
        d.rect(x0, yv - 0.05, x1, yv + 0.05, "glassfill", layer=3)

    # platibanda e paredes de divisa vistas de cima
    for r in ((0.0, GARAGEM_L, 0.15, LOTE_L), (3.85, GARAGEM_L, 4.0, LOTE_L),
              (0.15, *Y_FRENTE[:1], 3.85, Y_FRENTE[1]), (0.15, Y_FUNDO[0], 3.85, Y_FUNDO[1])):
        d.wall(*r)

    # calhas nos pontos baixos
    for y in (Y_FRENTE[1] + 0.08, Y_SALA[1], Y_Q1[1], Y_FUNDO[0] - 0.08):
        d.line([(0.15, y), (3.85, y)], "gutter", layer=3)
    # domus
    for cx, cy, s in DOMUS:
        h = s / 2
        d.rect(cx - h, cy - h, cx + h, cy + h, "domus", layer=3)
        d.circle((cx, cy), h * 0.7, "domusin", layer=3)

    # setas de caimento
    slope_arrow(d, 3.40, 7.55, 6.00, "5%")
    slope_arrow(d, 3.40, 11.65, 10.65, "5%")
    slope_arrow(d, 3.40, 17.00, 15.10, "5%")
    for nome, yv, ye, x0, x1 in SHEDS:
        pct = round(100 * (Z_SHED - Z_COB) / (ye - yv))
        slope_arrow(d, 3.40, yv + 0.30, ye - 0.30, f"{pct}%")

    # rótulos
    d.label((2.0, 2.70), "PERGOLADO", "vigas de madeira a cada 0,50", size=0.20, sub=0.14)
    for nome, yv, ye, x0, x1 in SHEDS:
        d.label((1.75, (yv + ye) / 2), nome.upper(), "janela alta voltada para a rua", size=0.18, sub=0.13)
    d.text((1.75, 6.80), "telha termoacústica", size=0.13, cls="tiny2")
    d.text((1.40, 11.15), "laje / telha", size=0.12, cls="tiny2")
    d.text((1.30, 16.55), "telha", size=0.12, cls="tiny2")
    d.text((-0.25, 10.35), "calha", size=0.12, cls="accenttext")
    d.text((-0.25, 14.80), "calha", size=0.12, cls="accenttext")
    d.text((-0.25, 5.80), "calha", size=0.12, cls="accenttext")
    d.text((-0.25, 19.75), "calha", size=0.12, cls="accenttext")
    d.text((2.0, -1.05), "CALÇADA", size=0.15, cls="tiny2", rot=-90)
    for (nome, yv, ye, x0, x1), cod in zip(SHEDS, ("JS1", "JS2", "JS3")):
        d.text((x0 - 0.30, yv), cod, size=0.12, cls="code")

    dim_chain(d, 1, 4.45, [Y_FRENTE[0], SHEDS[0][1], SHEDS[0][2], SHEDS[1][1], SHEDS[1][2], SHEDS[2][1],
                           SHEDS[2][2], LOTE_L], ext=4.0)
    section_marks(d, ys=(-2.15, 21.30))
    scale_bar(d, (4.85, -2.45))
    d.finalize()
    return d


# --------------------------------------------------------------------------
# CORTE AA (x = 2,00, vista para a direita)
# --------------------------------------------------------------------------
def corte_aa():
    d = Drawing("corte", plano=False)
    U0 = -2.2
    d.area(box(U0, -0.45, 20.25, 0.0), "terrain")
    d.line([(U0, -0.15), (-1.9, -0.15), (-1.9, 0.0), (20.25, 0.0)], "ground", layer=3)

    s = []
    s.append(box(0.0, -0.10, GARAGEM_L, Z_GARAGEM))                       # piso drenante
    s.append(box(GARAGEM_L, -0.10, LOTE_L, Z_PISO))                       # contrapiso da casa
    s.append(box(5.50, Z_PISO, 5.65, Z_PISO + 1.00))                      # fachada: peitoril J1
    s.append(box(5.50, Z_PISO + 2.20, 5.65, Z_PLATIBANDA))                # verga + platibanda
    for y0, y1 in ((Y_SALA[1], Y_LAV[0]), (Y_LAV[1], Y_Q1[0]), (Y_Q1[1], Y_BAN[0]), (Y_BAN[1], Y_Q2[0])):
        s.append(box(y0, Z_PISO, y1, Z_COB))
    s.append(box(Y_FUNDO[0], Z_PISO, LOTE_L, Z_PLATIBANDA))               # fundo + platibanda
    s.append(box(SHEDS[0][1] - 0.06, Z_FORRO, SHEDS[0][1] + 0.06, Z_COB))  # viga sob o vidro do shed 1
    # coberturas planas
    for y0, y1 in ((Y_FRENTE[1], SHEDS[0][1] - 0.06), (Y_LAV[0] - 0.10, SHEDS[1][1] - 0.05),
                   (Y_BAN[0] - 0.10, SHEDS[2][1] - 0.05)):
        s.append(box(y0, Z_COB - 0.12, y1, Z_COB))
    # sheds
    for nome, yv, ye, x0, x1 in SHEDS:
        s.append(box(yv - 0.06, Z_VIDRO_TOPO, yv + 0.06, Z_SHED))
        s.append(Polygon([(yv, Z_SHED - 0.12), (yv, Z_SHED), (ye, Z_COB), (ye, Z_COB - 0.12)]))
    # pergolado: viga frontal e vigas transversais (cortadas)
    s.append(box(0.0, 2.40, 0.15, Z_MURO))
    for i in range(11):
        y = 0.40 + i * 0.50
        s.append(box(y - 0.03, Z_MURO - 0.20, y + 0.03, Z_MURO))
    massa = unary_union(s)
    d.area(massa, "cut", layer=2)

    # forro: plano e inclinado sob os sheds
    for y0, y1 in ((Y_FRENTE[1], SHEDS[0][1] - 0.06), (Y_LAV[0], Y_LAV[1]), (Y_BAN[0], Y_BAN[1])):
        d.line([(y0, Z_FORRO), (y1, Z_FORRO)], "forro", layer=3)
    for nome, yv, ye, x0, x1 in SHEDS:
        y_in = yv + 0.06
        d.line([(y_in, Z_VIDRO_TOPO - 0.05), (ye, Z_FORRO)], "forro", layer=3)
        d.line([(yv - 0.02, Z_COB), (yv - 0.02, Z_VIDRO_TOPO)], "glassline", layer=3)
        d.line([(yv + 0.02, Z_COB), (yv + 0.02, Z_VIDRO_TOPO)], "glassline", layer=3)
    # calhas
    for y in (Y_FRENTE[1] + 0.10, Y_SALA[1], Y_Q1[1], Y_FUNDO[0] - 0.10):
        d.poly([(y - 0.08, Z_COB + 0.02), (y - 0.08, Z_COB - 0.08), (y + 0.08, Z_COB - 0.08), (y + 0.08, Z_COB + 0.02)],
               "gutterfill", layer=3)
    # domus (lavabo e banho 1)
    for cx, cy, sd in DOMUS:
        if abs(cx - CORTE_X) <= sd / 2:
            h = sd / 2
            pts = [(cy - h + 2 * h * i / 16, Z_COB + 0.28 * math.sin(math.pi * i / 16)) for i in range(17)]
            d.line(pts, "glassline", layer=3)
            d.line([(cy - h, Z_COB), (cy - h, Z_FORRO)], "elevlight", layer=3)
            d.line([(cy + h, Z_COB), (cy + h, Z_FORRO)], "elevlight", layer=3)

    # esquadrias no corte
    d.rect(0.0, Z_GARAGEM, 0.05, Z_PORTAO, "leaf", layer=3)                 # portão
    d.line([(5.555, Z_PISO + 1.00), (5.555, Z_PISO + 2.20)], "glassline", layer=3)
    d.line([(5.595, Z_PISO + 1.00), (5.595, Z_PISO + 2.20)], "glassline", layer=3)
    # muro da garagem visto ao fundo
    d.line([(0.0, Z_MURO), (GARAGEM_L, Z_MURO)], "elevlight", layer=1)

    # luz natural entrando pelos sheds (raios interrompidos no primeiro obstáculo)
    alvo = massa.buffer(-0.001)
    for nome, yv, ye, x0, x1 in SHEDS:
        for zj in (3.35, 3.70):
            p0 = (yv - 0.45, zj + 0.57)
            pj = (yv, zj)
            dx, dz = pj[0] - p0[0], pj[1] - p0[1]
            k = (pj[1] - 1.75) / -dz
            far = (pj[0] + dx * k, 1.75)
            ray = LineString([(pj[0] + 0.07, pj[1] + dz / dx * 0.07), far])
            end = far
            hit = ray.intersection(alvo)
            if not hit.is_empty:
                pts = []
                for g in getattr(hit, "geoms", [hit]):
                    pts += list(g.coords)
                end = min(pts, key=lambda q: math.dist(q, pj))
            d.line([p0, end], "light", layer=1)

    # rótulos
    zt = Z_PISO + 1.15
    d.text((2.75, 1.30), "GARAGEM", size=0.22, cls="label")
    d.text((2.75, 0.98), "pergolado + piso drenante", size=0.13, cls="tiny2")
    d.text((7.10, zt + 0.55), "SALA + COZINHA", size=0.19, cls="label")
    d.text((11.15, zt + 0.12), "LAVABO +", size=0.13, cls="label")
    d.text((11.15, zt - 0.10), "LAVAND.", size=0.13, cls="label")
    d.text((13.38, zt), "SUÍTE 1", size=0.19, cls="label")
    d.text((16.00, zt), "BANHO 1", size=0.16, cls="label")
    d.text((18.52, zt), "SUÍTE 2", size=0.19, cls="label")
    for nome, yv, ye, x0, x1 in SHEDS:
        d.text((yv + 0.75, Z_SHED + 0.32), nome, size=0.14, cls="accenttext")
    d.text((10.90, 3.62), "domus", size=0.12, cls="tiny2")
    d.text((15.95, 3.62), "domus", size=0.12, cls="tiny2")

    for z, t in ((Z_CALCADA, "±0,00 calçada"), (Z_PISO, f"+{fmt(Z_PISO)} piso"),
                 (Z_FORRO, f"+{fmt(Z_FORRO)} forro"), (Z_PLATIBANDA, f"+{fmt(Z_PLATIBANDA)} platibanda"),
                 (Z_SHED, f"+{fmt(Z_SHED)} topo dos sheds")):
        d.poly([(20.45, z), (20.33, z + 0.13), (20.57, z + 0.13)], "levelmark", layer=4)
        d.line([(20.25, z), (20.70, z)], "dim", layer=4)
        d.text((20.75, z + 0.12), t, size=0.15, cls="dimtext", anchor="start", layer=5)

    dim_chain(d, 1, -0.65, [0.0, Z_PISO, Z_FORRO, Z_PLATIBANDA], ext=0.0, labels=[None, "2,70", "0,65"])
    dim_chain(d, 1, -1.25, [0.0, Z_SHED], ext=0.0)
    dim_chain(d, 0, -0.85, [0.0, GARAGEM_L, LOTE_L], toff=-0.17, labels=["5,50", "14,50"])
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
    # ao fundo (5,50 m atrás): fachada da casa, platibanda e shed 1
    d.area(box(0.0, Z_MURO, 4.0, Z_PLATIBANDA), "facade2", layer=0)
    d.area(box(0.0, Z_PLATIBANDA, 4.0, Z_SHED), "facade3", layer=0)
    x0, x1 = SHEDS[0][3], SHEDS[0][4]
    d.area(box(x0, Z_PLATIBANDA, x1, Z_VIDRO_TOPO), "glasspane", layer=1)
    d.rect(x0, Z_PLATIBANDA, x1, Z_VIDRO_TOPO, "frame", layer=3)
    for u in (x0 + (x1 - x0) / 3, x0 + 2 * (x1 - x0) / 3):
        d.line([(u, Z_PLATIBANDA), (u, Z_VIDRO_TOPO)], "frame", layer=3)
    d.line([(0.0, Z_PLATIBANDA), (4.0, Z_PLATIBANDA)], "elev", layer=3)
    d.rect(0.0, Z_MURO, 4.0, Z_SHED, "elev", layer=3)
    # vão entre portões e pergolado (sombra da garagem)
    d.area(box(0.15, Z_PORTAO, 3.85, 2.40), "shadow", layer=1)
    # primeiro plano: muros, pilar, viga do pergolado, portões
    d.area(unary_union([box(0.0, 0.0, 0.15, Z_MURO), box(3.85, 0.0, 4.0, Z_MURO),
                        box(1.05, 0.0, 1.15, 2.40)]), "facade", layer=2)
    d.area(box(0.15, 2.40, 3.85, Z_MURO), "wood", layer=2)
    d.rect(0.15, 2.40, 3.85, Z_MURO, "frame", layer=3)
    for a, b in ((0.15, 1.05), (1.15, 3.85)):
        d.area(box(a, 0.0, b, Z_PORTAO), "gate", layer=3)
        n = int((b - a) / 0.11)
        for i in range(1, n):
            u = a + i * (b - a) / n
            d.line([(u, 0.05), (u, Z_PORTAO - 0.05)], "slat2", layer=3)
        d.rect(a, 0.0, b, Z_PORTAO, "frame", layer=3)
    d.line([(0.90, 0.95), (0.90, 1.20)], "frame", layer=3)

    notes = [
        (4.40, (1.10, 3.75), "Shed 1 — janela alta (sala e cozinha)"),
        (3.70, (3.60, 3.20), "Platibanda — reboco e pintura"),
        (2.85, (2.80, 2.60), "Pergolado de madeira sobre a garagem"),
        (1.60, (2.50, 1.60), "Portão basculante ripado, 2,70 × 2,20"),
        (0.80, (0.60, 0.80), "Portão social, 0,90 × 2,20"),
        (0.25, (3.92, 0.40), "Muro de divisa, h = 2,80"),
    ]
    for z, (u0, z0), t in notes:
        d.line([(u0, z0), (4.35, z), (4.55, z)], "leader", layer=4)
        d.circle((u0, z0), 0.035, "leaderdot", layer=4)
        d.text((4.62, z), t, size=0.15, cls="note", anchor="start")

    dim_chain(d, 0, -0.55, [0.0, 0.15, 3.85, 4.0], ext=0.0, toff=-0.17)
    dim_chain(d, 0, -1.00, [0.0, 4.0], ext=0.0, toff=-0.17)
    dim_chain(d, 1, -0.45, [0.0, Z_PORTAO, Z_MURO, Z_PLATIBANDA, Z_SHED], ext=0.0, label_min=0.5)
    dim_chain(d, 1, -0.95, [0.0, Z_SHED], ext=0.0)
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
  .grasspave{fill:#e7eedf}
  .pergola{fill:none;stroke:#a4835f;stroke-width:.7;stroke-dasharray:5 4}
  .pergbeam{fill:#c49a6c;stroke:#7e5532;stroke-width:.5}
  .roofflat{fill:#e3e6e8}
  .roofshed{fill:#cfd5da}
  .roofline{fill:none;stroke:#aeb5bc;stroke-width:.5}
  .shededge{fill:#22262b}
  .gutter{fill:none;stroke:#2f6db3;stroke-width:.9;stroke-dasharray:6 3}
  .gutterfill{fill:#ffffff;stroke:#22262b;stroke-width:.6}
  .domus{fill:#dbe8f3;stroke:#2f6db3;stroke-width:.8}
  .domusin{fill:none;stroke:#2f6db3;stroke-width:.6}
  .skylightbox{fill:none;stroke:#2f6db3;stroke-width:.6;stroke-dasharray:3 2}
  .slope{fill:none;stroke:#3b4249;stroke-width:.8}
  .slopehead{fill:#3b4249}
  .forro{fill:none;stroke:#59616a;stroke-width:1.6}
  .facade2{fill:#d9d5cd}
  .facade3{fill:#cbc6bd}
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
    "pergbeam": "PERGOLADO", "pergola": "PERGOLADO", "roofflat": "COBERTURA", "roofshed": "COBERTURA",
    "roofline": "COBERTURA", "shededge": "COBERTURA", "gutter": "COBERTURA", "domus": "COBERTURA",
    "domusin": "COBERTURA", "skylightbox": "PROJECOES", "forro": "CORTE-ELEMENTOS",
}
LAYER_COLORS = {"PAREDES": 7, "MUROS": 8, "ESQUADRIAS": 5, "MOBILIARIO": 8, "COTAS": 3, "TEXTOS": 7,
                "ESCADA": 7, "PROJECOES": 9, "CORTE-INDICACAO": 1, "CORTE-ELEMENTOS": 7, "FACHADA": 7,
                "PISOS": 9, "VISTAS": 8, "PERGOLADO": 32, "COBERTURA": 8}


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



FONTS = ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700"
         "&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;600&display=swap")


PAGE_CSS = r"""
/* Layout: prancha de desenho — desenhos largos alinhados pelo mesmo eixo de profundidade, texto em coluna estreita */
:root{
  --bg:#e9ece8; --sheet:#fbfbf9; --ink:#1b1f23; --ink2:#4a535b; --rule:#c6ccc8;
  --poche:#22262a; --furn:#8b939a; --furn2:#b4bac0; --accent:#2a60a6; --mark:#c2410c; --sun:#cf9300;
  --garage:#edefef; --wet:#e1ebf1; --wetbox:#d3e2ec; --garden:#dcebcf; --gardenline:#7a9c6b; --walk:#e5e3dd;
  --terrainbg:#eeece6; --terrainline:#b8b1a3; --roof:#7b838b; --muro:#9aa1a8; --murol:#5f666d;
  --facade:#e6e2da; --recess:#d4d0c7; --shadow:#3a3f45; --wood:#b9855a; --woodline:#7e5532;
  --gate:#4a5057; --gateline:#2a2e33; --glasspane:#a9c4dc; --glassrail:#cfe0ee; --plant:#8fb37c; --reflect:#ffffff;
  --grass:#e4ecdb; --roofflat:#e2e5e7; --roofshed:#ccd2d7; --facade2:#d8d4cc; --facade3:#c9c4bb;
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
  --grass:#1e2a1c; --roofflat:#22272b; --roofshed:#2b3238; --facade2:#2a2e33; --facade3:#33383d;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#111417; --sheet:#181c20; --ink:#e4e8eb; --ink2:#a2abb3; --rule:#2e353b;
  --poche:#dde2e6; --furn:#76808a; --furn2:#4f575f; --accent:#79adf0; --mark:#f4844a; --sun:#f2b733;
  --garage:#1f2428; --wet:#1a2630; --wetbox:#21313d; --garden:#1c2a1b; --gardenline:#5f8a52; --walk:#22252a;
  --terrainbg:#1d2023; --terrainline:#3c4248; --roof:#8a939b; --muro:#59626a; --murol:#8a939b;
  --facade:#2f3338; --recess:#262a2f; --shadow:#0c0e10; --wood:#9a6b45; --woodline:#5f3f22;
  --gate:#5a626a; --gateline:#3a4046; --glasspane:#3d5a75; --glassrail:#2c4256; --plant:#5f8a52; --reflect:#c9d8e6;
  --grass:#1e2a1c; --roofflat:#22272b; --roofshed:#2b3238; --facade2:#2a2e33; --facade3:#33383d;
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
.dwg .grasspave{fill:var(--grass)}
.dwg .pergola{fill:none;stroke:var(--woodline);stroke-width:.7;stroke-dasharray:5 4;opacity:.7}
.dwg .pergbeam{fill:var(--wood);stroke:var(--woodline);stroke-width:.5}
.dwg .roofflat{fill:var(--roofflat)}
.dwg .roofshed{fill:var(--roofshed)}
.dwg .roofline{fill:none;stroke:var(--furn2);stroke-width:.5}
.dwg .shededge{fill:var(--poche)}
.dwg .gutter{fill:none;stroke:var(--accent);stroke-width:.9;stroke-dasharray:6 3}
.dwg .gutterfill{fill:var(--sheet);stroke:var(--ink);stroke-width:.6}
.dwg .domus{fill:var(--wet);stroke:var(--accent);stroke-width:.8}
.dwg .domusin{fill:none;stroke:var(--accent);stroke-width:.6}
.dwg .skylightbox{fill:none;stroke:var(--accent);stroke-width:.6;stroke-dasharray:3 2}
.dwg .slope{fill:none;stroke:var(--ink2);stroke-width:.8}
.dwg .slopehead{fill:var(--ink2)}
.dwg .forro{fill:none;stroke:var(--ink2);stroke-width:1.6}
.dwg .facade2{fill:var(--facade2)}
.dwg .facade3{fill:var(--facade3)}
.dwg .barfill{fill:var(--ink);stroke:var(--ink);stroke-width:.6}
.dwg .barempty{fill:var(--sheet);stroke:var(--ink);stroke-width:.6}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""




def _e(t):
    return html.escape(t)


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
# Quadro de áreas e índices
# --------------------------------------------------------------------------
def quadro():
    a = areas()
    lote = LOTE_W * LOTE_L
    casa = LOTE_W * (LOTE_L - GARAGEM_L)          # 58,00 m² (paredes incluídas)
    garagem = LOTE_W * GARAGEM_L                  # 22,00 m² com pergolado
    util = sum(v for k, v in a.items() if k != "GARAGEM")
    linhas = [("Sala + cozinha integradas", a["SALA + COZINHA"]), ("Lavabo + lavanderia", a["LAVABO + LAVANDERIA"]),
              ("Circulação", a["CIRCULAÇÃO"]), ("Suíte 1 (quarto)", a["SUÍTE 1"]), ("Banho suíte 1", a["BANHO 1"]),
              ("Suíte 2 (quarto)", a["SUÍTE 2"]), ("Banho suíte 2", a["BANHO 2"])]
    return dict(linhas=linhas, garagem_util=a["GARAGEM"], util=util, casa=casa, garagem=garagem, lote=lote,
                to=casa / lote, ca=casa / lote, perm=a["GARAGEM"] / lote)


# --------------------------------------------------------------------------
# Textos do memorial (usados na página, na prancha e no README)
# --------------------------------------------------------------------------
PROGRAMA = [
    ("Garagem de 5,50 m ocupando toda a frente",
     "Garagem de 4,00 × 5,50 m (3,70 m livres entre os muros), com pergolado e piso drenante. Portão basculante "
     "de 2,70 m e portão social de 0,90 m. O carro fica à direita e a passagem para a porta de entrada, à esquerda."),
    ("Sala e cozinha conjugadas",
     "Um ambiente de 17,39 m² com estar, mesa para 4 e cozinha linear de 2,75 m (geladeira, pia e cooktop). "
     "Janela para a garagem e janela alta no shed sobre a cozinha."),
    ("Lavabo junto com a lavanderia",
     "Ambiente único de 3,85 m² logo depois da cozinha, com vaso, lavatório, tanque e máquina de lavar. "
     "Ventilação por domus no teto."),
    ("Duas suítes, tudo no térreo",
     "Suíte 1 com quarto de 7,84 m² e banheiro de 2,86 m². Suíte 2, no fundo, com quarto de 9,81 m² "
     "e banheiro de 2,97 m². Os dois banheiros ficam lado a lado, entre os quartos."),
]

PARTIDO = [
    ("O programa ocupa o lote inteiro",
     "Depois da garagem sobram 14,50 m de profundidade e 3,70 m livres de largura. Sala, lavabo, duas suítes e "
     "corredor cabem exatamente nesse espaço: a casa vai até o muro do fundo e não sobra quintal. "
     "Por isso os cômodos são compactos."),
    ("Luz e ar pelo telhado (sheds)",
     "As paredes laterais estão na divisa e não podem ter janelas (Código Civil, art. 1.301), e o fundo encosta "
     "no vizinho. A sala, a cozinha e os quartos recebem janelas altas em sheds, voltadas para a rua. Essas "
     "janelas ficam perpendiculares às divisas e a mais de 0,75 m delas, distância que o § 1º do mesmo artigo exige."),
    ("Um corredor só",
     "Um corredor de 0,85 m na lateral esquerda liga a sala ao lavabo, à suíte 1 e à suíte 2. "
     "A suíte do fundo ocupa a largura toda porque o corredor termina na porta dela."),
    ("Banheiros lado a lado",
     "Os banheiros das duas suítes ficam lado a lado, cada um abrindo para a sua suíte. Assim eles dividem a "
     "parede hidráulica e ocupam 2,20 m de comprimento em vez de 2,90 m."),
    ("Garagem aberta com pergolado",
     "Sem laje, a garagem funciona como área aberta: ilumina a sala, pode contar como área permeável (com piso "
     "drenante) e normalmente não entra na taxa de ocupação."),
]

MEMORIAL = [
    ("Alturas", "Pé-direito de 2,70 m. Sob os sheds, o forro acompanha a inclinação e sobe até cerca de 3,70 m junto "
                "à janela. Platibanda a 3,50 m e topo dos sheds a 4,05 m."),
    ("Estrutura", "Alvenaria estrutural de blocos de 14 cm ou concreto armado com pilares nas divisas. Cobertura em "
                  "estrutura metálica leve com telha termoacústica. O dimensionamento é do projeto estrutural."),
    ("Paredes", "Paredes de divisa com 15 cm acabadas e internas com 10 cm."),
    ("Cobertura", "Trechos planos com 5% de caimento e sheds com cerca de 35%, sempre escoando para longe das "
                  "janelas. Calhas nos pontos baixos, com descidas embutidas nas paredes de divisa."),
    ("Janelas dos sheds", "Basculantes de vidro entre 2,95 m e 3,75 m acima do piso, abertas por haste. Se a rua "
                          "ficar ao norte, use vidro de controle solar ou brise; se ficar ao sul, a luz entra difusa."),
    ("Banheiros e lavabo", "Domus ventilado no teto e exaustor com duto até a cobertura."),
    ("Iluminação", "As aberturas da sala e dos quartos somam pelo menos 1/6 da área de piso, a proporção que muitos "
                   "códigos de obras pedem para ambientes de permanência prolongada."),
    ("Área permeável", "Garagem com concregrama ou piso intertravado permeável."),
]

VERIFICAR = [
    ("Fundo e laterais na divisa", "A casa encosta nas duas laterais e no fundo. Algumas cidades exigem recuo de "
                                   "fundo ou área livre mínima no lote. Nesse caso, os cômodos precisam encolher ou "
                                   "volta a fazer sentido o sobrado."),
    ("Janelas em sheds", "A maioria dos códigos de obras aceita janelas altas voltadas para o céu como iluminação "
                         "e ventilação. Confirme no código do seu município."),
    ("Garagem no recuo frontal", "Pergolado no recuo costuma ser permitido. Se a prefeitura deixar cobrir com "
                                 "policarbonato ou telha, a garagem passa a contar como área coberta."),
    ("Índices urbanísticos", "Taxa de ocupação de 72,5% e coeficiente de aproveitamento de 0,725, sem contar a garagem. "
                             "A permeabilidade depende de a prefeitura aceitar o piso drenante da garagem (até 25,4%)."),
    ("Aprovação", "Este é um anteprojeto. Para construir, é preciso o projeto legal assinado por arquiteto ou "
                  "engenheiro (RRT/ART), além dos projetos estrutural, elétrico e hidrossanitário."),
]

ESQUADRIAS = [
    ("P1", "Porta de entrada, de giro", "0,90 × 2,10", "—", 1),
    ("P2", "Porta de giro (lavabo + lavanderia)", "0,70 × 2,10", "—", 1),
    ("P3", "Porta de giro (suítes)", "0,80 × 2,10", "—", 2),
    ("P4", "Porta de giro (banheiros)", "0,60 × 2,10", "—", 2),
    ("J1", "Janela de correr (sala → garagem)", "1,50 × 1,20", "1,00", 1),
    ("JS1", "Janela alta basculante no shed 1 (sala e cozinha)", "2,50 × 0,80", "2,95", 1),
    ("JS2", "Janela alta basculante no shed 2 (suíte 1)", "2,00 × 0,80", "2,95", 1),
    ("JS3", "Janela alta basculante no shed 3 (suíte 2)", "2,50 × 0,80", "2,95", 1),
    ("D1", "Domus ventilado (lavabo + lavanderia)", "0,80 × 0,80", "teto", 1),
    ("D2", "Domus ventilado (banheiros e corredor)", "0,60 × 0,60", "teto", 4),
    ("PG", "Portão basculante ripado", "2,70 × 2,20", "—", 1),
    ("PS", "Portão social ripado", "0,90 × 2,20", "—", 1),
]


# --------------------------------------------------------------------------
# Página HTML (artifact)
# --------------------------------------------------------------------------
def tabela_areas(q):
    rows = ['<tr class="grp"><td colspan="2">Casa</td></tr>']
    rows += [f'<tr><td>{_e(n)}</td><td class="n">{fmt(v)}</td></tr>' for n, v in q["linhas"]]
    rows.append(f'<tr class="sum"><td>Área útil da casa</td><td class="n">{fmt(q["util"])}</td></tr>')
    rows.append('<tr class="grp"><td colspan="2">Área construída</td></tr>')
    rows.append(f'<tr class="total"><td>Casa (4,00 × 14,50, com paredes)</td><td class="n">{fmt(q["casa"])} m²</td></tr>')
    rows.append(f'<tr><td>Garagem com pergolado (área aberta)</td><td class="n">{fmt(q["garagem_util"])}</td></tr>')
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

    def itens(lst):
        return "".join(f'<div class="item"><h3>{_e(t)}</h3><p>{_e(x)}</p></div>' for t, x in lst)

    programa = "".join(f'<li><span class="ok">✓ atendido</span><h3>{_e(t)}</h3><p>{_e(x)}</p></li>' for t, x in PROGRAMA)
    return f"""<title>Casa Térrea 4×20</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{PAGE_CSS}</style>
<div class="wrap">
  <header class="head">
    <div class="intro">
      <span class="eyebrow">Anteprojeto residencial · lote 4 × 20 m · um pavimento</span>
      <h1>Casa Térrea 4×20</h1>
      <p class="lede">Casa térrea com duas suítes, sala e cozinha integradas, lavabo junto com a lavanderia e
      garagem de 5,50 m ocupando toda a frente do lote. Luz e ventilação entram por sheds no telhado.</p>
    </div>
    <dl class="carimbo">
      <div><dt>Lote</dt><dd>4,00 × 20,00 m</dd></div>
      <div><dt>Área do lote</dt><dd>{fmt(q['lote'])} m²</dd></div>
      <div><dt>Área construída</dt><dd>{fmt(q['casa'])} m²</dd></div>
      <div><dt>Pavimentos</dt><dd>1 (térreo)</dd></div>
      <div><dt>Quartos</dt><dd>2 suítes</dd></div>
      <div><dt>Altura máxima</dt><dd>4,05 m</dd></div>
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
      <span><i class="lg-glass"></i>vidro, janela alta, domus</span>
      <span><i class="lg-proj"></i>projeção (pergolado, cobertura)</span>
      <span><i class="lg-sec"></i>linha de corte AA</span>
      <span><i class="lg-sun"></i>luz pelos sheds</span>
    </div>
    <div class="set">
      {fig("planta-baixa", "Planta baixa", "rua à esquerda · cotas em metros")}
      {fig("planta-cobertura", "Planta de cobertura", "sheds, domus e calhas")}
      {fig("corte-aa", "Corte AA", "longitudinal, pela faixa dos quartos")}
    </div>
  </section>

  <section class="duo" aria-label="Fachada e quadro de áreas">
    {fig("fachada-frontal", "Fachada frontal", "vista da rua", small=True)}
    <div class="tablebox">
      <h3 style="padding:10px 0 4px;text-transform:uppercase;letter-spacing:.05em">Quadro de áreas</h3>
      {tabela_areas(q)}
      <div class="indices">
        <div><b>{fmt(q['to'] * 100, 1)}%</b><small>taxa de ocupação</small></div>
        <div><b>{fmt(q['ca'], 3)}</b><small>coef. de aproveitamento</small></div>
        <div><b>até {fmt(q['perm'] * 100, 1)}%</b><small>área permeável</small></div>
      </div>
    </div>
  </section>

  <section aria-labelledby="h-part">
    <h2 id="h-part">Como a casa foi resolvida</h2>
    <div class="cols">{itens(PARTIDO)}</div>
  </section>

  <section aria-labelledby="h-esq">
    <h2 id="h-esq">Quadro de esquadrias</h2>
    <div class="tablebox"><div class="scroll">{tabela_esquadrias()}</div></div>
  </section>

  <section aria-labelledby="h-mem">
    <h2 id="h-mem">Memorial resumido</h2>
    <div class="cols">{itens(MEMORIAL)}</div>
  </section>

  <section class="aviso" aria-labelledby="h-ver">
    <h2 id="h-ver">Antes de construir, verifique</h2>
    <div class="cols">{itens(VERIFICAR)}</div>
  </section>

  <footer class="files">
    <h3>Arquivos no repositório</h3>
    <p><code>projeto/prancha-a3.pdf</code> prancha única em A3, escala 1:100, para imprimir e levar ao arquiteto ou engenheiro.</p>
    <p><code>projeto/casa-terrea-4x20.dxf</code> planta, cobertura, corte e fachada para AutoCAD, em metros e separados por camadas.</p>
    <p><code>gerar_projeto.py</code> modelo paramétrico que gera todos os desenhos e o quadro de áreas.</p>
  </footer>
</div>
"""


# --------------------------------------------------------------------------
# Prancha A3 (1:100) para PDF
# --------------------------------------------------------------------------
def prancha_html(S, q):
    blocks = {}
    for key, d in DRAWINGS.items():
        kw = {"xrange": XR} if key != "fachada-frontal" else {"extra": (0, 0, 4.3, 0)}
        sa, T = to_svg(d, s=S, uid="p" + key, standalone=True, **kw)
        w_mm, h_mm = T.W / S * 10.0, T.H / S * 10.0        # 1:100 -> 1 m = 10 mm
        blocks[key] = sa.replace(f'width="{T.W:.0f}" height="{T.H:.0f}"',
                                 f'width="{w_mm:.2f}mm" height="{h_mm:.2f}mm"', 1)

    areas_rows = "".join(f"<tr><td>{_e(n)}</td><td class='n'>{fmt(v)}</td></tr>" for n, v in q["linhas"])
    esq_rows = "".join(f"<tr><td>{c}</td><td>{_e(t.split(' (')[0])}</td><td class='n'>{d}</td><td class='n'>{pt}</td>"
                       f"<td class='n'>{n}</td></tr>" for c, t, d, pt, n in ESQUADRIAS)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS}">
<style>
@page{{size:420mm 297mm;margin:0}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Source Sans 3',Arial,sans-serif;color:#1b1f23;background:#fff}}
.sheet{{width:420mm;height:297mm;padding:9mm 10mm;position:relative;display:grid;grid-template-columns:257mm 1fr;gap:0 7mm}}
.frame{{position:absolute;inset:6mm;border:.5mm solid #1b1f23;pointer-events:none}}
.col{{display:flex;flex-direction:column;gap:1.2mm;min-width:0}}
h4{{font-family:'Barlow Condensed',Arial Narrow,sans-serif;font-size:10pt;letter-spacing:.06em;margin:1.6mm 0 0;
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
  <h4>Planta baixa <span>esc. 1:100</span></h4>{blocks['planta-baixa']}
  <h4>Planta de cobertura <span>esc. 1:100</span></h4>{blocks['planta-cobertura']}
  <h4>Corte AA <span>esc. 1:100</span></h4>{blocks['corte-aa']}
</div>
<div class="col">
  <h4>Fachada frontal <span>esc. 1:100</span></h4>{blocks['fachada-frontal']}
  <h4>Quadro de áreas (m²)</h4>
  <table>{areas_rows}
    <tr><td>Área útil da casa</td><td class='n'>{fmt(q['util'])}</td></tr>
    <tr><td>Garagem com pergolado (área aberta)</td><td class='n'>{fmt(q['garagem_util'])}</td></tr>
    <tr class="tot"><td>Área construída (casa, 4,00 × 14,50)</td><td class='n'>{fmt(q['casa'])}</td></tr>
    <tr><td>Taxa de ocupação · Coef. aproveitamento · Permeável</td><td class='n'>{fmt(q['to']*100,1)}% · {fmt(q['ca'], 3)} · {fmt(q['perm']*100,1)}%</td></tr>
  </table>
  <h4>Quadro de esquadrias</h4>
  <table><tr><th>Cód.</th><th>Tipo</th><th class="n">L × H</th><th class="n">Peit.</th><th class="n">Qtd</th></tr>{esq_rows}</table>
  <p class="obs">Pé-direito 2,70 m; forro inclinado sob os sheds. Paredes laterais e de fundo cegas (Código Civil, art. 1.301);
  janelas dos sheds perpendiculares às divisas e a mais de 0,75 m delas. Banheiros e lavabo com domus ventilado e exaustor.
  Verificar recuos, índices e aceitação dos sheds no código de obras do município.</p>
  <div class="carimbo">
    <div class="full t"><small>Projeto</small><b>Casa Térrea 4×20 — anteprojeto</b></div>
    <div><small>Lote</small><b>4,00 × 20,00 m ({fmt(q['lote'])} m²)</b></div>
    <div><small>Área construída</small><b>{fmt(q['casa'])} m²</b></div>
    <div><small>Escala</small><b>1:100 (A3)</b></div>
    <div><small>Data</small><b>nov/2026</b></div>
    <div class="full"><small>Observação</small><b style="font-size:7.5pt;font-family:'Source Sans 3',Arial,sans-serif;font-weight:400">
    Estudo preliminar. Não substitui o projeto legal assinado por responsável técnico (RRT/ART).</b></div>
  </div>
</div>
</div></body></html>"""


# --------------------------------------------------------------------------
# README
# --------------------------------------------------------------------------
CADEIA = [("Garagem", 0.00, 5.50), ("Sala + cozinha", 5.65, 10.35), ("Lavabo + lavanderia", 10.45, 11.85),
          ("Suíte 1 (quarto)", 11.95, 14.80), ("Banheiros lado a lado", 14.90, 17.10), ("Suíte 2 (quarto)", 17.20, 19.85)]


def readme_md(q):
    L = ["# Casa Térrea 4×20 — anteprojeto", "",
         "Casa de **um pavimento** para um lote de **4,00 × 20,00 m**: duas suítes, sala e cozinha integradas, "
         "lavabo junto com a lavanderia e garagem de **5,50 m** ocupando toda a frente do terreno.", "",
         f"**Área construída:** {fmt(q['casa'])} m² (+ garagem com pergolado) · **Área útil:** {fmt(q['util'])} m² · "
         f"**Taxa de ocupação:** {fmt(q['to'] * 100, 1)}% · **Permeável:** até {fmt(q['perm'] * 100, 1)}%", "",
         "## Programa pedido", ""]
    L += [f"- **{t}** — {x}" for t, x in PROGRAMA]
    L += ["", "## Como os 20 m foram distribuídos", "", "| Trecho | de (m) | até (m) | comprimento |", "|---|---:|---:|---:|"]
    L += [f"| {n} | {fmt(a)} | {fmt(b)} | {fmt(b - a)} |" for n, a, b in CADEIA]
    L += ["", "Entre os trechos há paredes de 10 a 15 cm; a parede do fundo termina exatamente em 20,00 m.", "",
          "## Desenhos", "", "As plantas estão com a rua à esquerda; plantas e corte usam a mesma escala e o mesmo eixo.", "",
          "### Planta baixa", "", "![Planta baixa](projeto/planta-baixa.svg)", "",
          "### Planta de cobertura", "", "![Planta de cobertura](projeto/planta-cobertura.svg)", "",
          "### Corte AA", "", "![Corte AA](projeto/corte-aa.svg)", "",
          "### Fachada frontal", "", "![Fachada frontal](projeto/fachada-frontal.svg)", "",
          "## Quadro de áreas", "", "| Ambiente | m² |", "|---|---:|"]
    L += [f"| {n} | {fmt(v)} |" for n, v in q["linhas"]]
    L += [f"| **Área útil da casa** | **{fmt(q['util'])}** |",
          f"| Garagem com pergolado (área aberta) | {fmt(q['garagem_util'])} |",
          f"| **Área construída** (casa 4,00 × 14,50) | **{fmt(q['casa'])}** |", "",
          "## Como a casa foi resolvida", ""]
    L += [f"- **{t}.** {x}" for t, x in PARTIDO]
    L += ["", "## Quadro de esquadrias", "", "| Cód. | Tipo | L × H (m) | Peitoril | Qtd. |", "|---|---|---:|---:|---:|"]
    L += [f"| {c} | {t} | {d} | {pt} | {n} |" for c, t, d, pt, n in ESQUADRIAS]
    L += ["", "## Memorial resumido", ""] + [f"- **{t}.** {x}" for t, x in MEMORIAL]
    L += ["", "## Antes de construir, verifique", ""] + [f"- **{t}.** {x}" for t, x in VERIFICAR]
    L += ["", "## Arquivos", "", "| Arquivo | Conteúdo |", "|---|---|",
          "| `projeto/prancha-a3.pdf` | Prancha única A3 em escala 1:100 (planta, cobertura, corte, fachada, quadros) |",
          "| `projeto/casa-terrea-4x20.dxf` | Desenhos para CAD, em metros, separados por camadas |",
          "| `projeto/*.svg` | Desenhos em vetor |",
          "| `projeto/index.html` | Página de apresentação (tema claro e escuro) |",
          "| `gerar_projeto.py` | Modelo paramétrico que gera todos os arquivos acima |",
          "", "A primeira versão (sobrado de dois pavimentos) está no histórico do git, no commit `9a2be4c`.", "",
          "Para alterar o projeto, edite as coordenadas em `gerar_projeto.py` e rode:", "",
          "```bash", "pip install shapely ezdxf", "python3 gerar_projeto.py   # o PDF usa node + playwright, se houver", "```", ""]
    return "\n".join(L)


DRAWINGS = {}
XR = (-2.75, 22.75)


def main():
    global DRAWINGS
    os.makedirs(OUT, exist_ok=True)
    DRAWINGS = {"planta-baixa": planta_baixa(), "planta-cobertura": planta_cobertura(),
                "corte-aa": corte_aa(), "fachada-frontal": fachada()}
    S = 56
    svgs = {}
    for key, d in DRAWINGS.items():
        kw = {"xrange": XR} if key != "fachada-frontal" else {"extra": (0, 0, 4.3, 0)}
        sa, _ = to_svg(d, s=S, uid=key, standalone=True, **kw)
        with open(os.path.join(OUT, f"{key}.svg"), "w", encoding="utf-8") as f:
            f.write(sa)
        svgs[key] = to_svg(d, s=S, uid=key, standalone=False, **kw)

    to_dxf([(DRAWINGS["planta-baixa"], (0, 0), "PLANTA BAIXA"),
            (DRAWINGS["planta-cobertura"], (0, -9), "PLANTA DE COBERTURA"),
            (DRAWINGS["corte-aa"], (0, -20), "CORTE AA"),
            (DRAWINGS["fachada-frontal"], (27, -20), "FACHADA FRONTAL")],
           os.path.join(OUT, "casa-terrea-4x20.dxf"))

    q = quadro()
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina_html(svgs, q))
    prancha = os.path.join(OUT, "prancha-a3.html")
    with open(prancha, "w", encoding="utf-8") as f:
        f.write(prancha_html(S, q))
    ok = gerar_pdf(prancha, os.path.join(OUT, "prancha-a3.pdf"))
    with open(os.path.join(RAIZ, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_md(q))
    print(f"Área construída: {fmt(q['casa'])} m² | útil: {fmt(q['util'])} m² | TO {fmt(q['to'] * 100, 1)}% | "
          f"permeável até {fmt(q['perm'] * 100, 1)}%")
    print("Arquivos em", OUT, "(PDF ok)" if ok else "(sem PDF)")


if __name__ == "__main__":
    main()
