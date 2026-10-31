"""Small native ttk theme; checkbox indicators are explicit ticks, not theme crosses."""
import math
import tkinter as tk
from tkinter import ttk

BG = '#0d141d'
PANEL = '#17222e'
FIELD = '#101a25'
TEXT = '#edf5f7'
MUTED = '#96a9b9'
ACCENT = '#75e0c2'
BORDER = '#2b3b49'


def tick_image(root, size, selected, disabled=False, hover=False):
    """Rasterize a rounded square and two joined tick strokes at the current DPI."""
    image = tk.PhotoImage(master=root, width=size, height=size)
    fill = '#35554f' if disabled else ACCENT
    border = ACCENT if hover else BORDER
    ink = '#0d2925' if not disabled else '#a0b9b3'

    def distance(x, y, ax, ay, bx, by):
        t = max(0, min(1, ((x-ax)*(bx-ax)+(y-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2)))
        return math.hypot(x-ax-t*(bx-ax), y-ay-t*(by-ay))

    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            x, y = (px+.5)/size, (py+.5)/size
            dx, dy = max(abs(x-.5)-.30, 0), max(abs(y-.5)-.30, 0)
            d = math.hypot(dx, dy)
            color = PANEL
            if d < .16:
                color = fill if selected else border
            if d < .10 and not selected:
                color = FIELD
            if selected and min(distance(x,y,.25,.51,.43,.68), distance(x,y,.43,.68,.76,.33)) < .055:
                color = ink
            row.append(color)
        rows.append('{'+' '.join(row)+'}')
    image.put(' '.join(rows))
    return image


def install(root, scale):
    style = ttk.Style(root)
    style.theme_use('clam')
    p = lambda value: round(value * scale)
    style.configure('.', font=('Microsoft YaHei UI', 10), background=BG, foreground=TEXT)
    style.configure('TFrame', background=BG)
    style.configure('Card.TFrame', background=PANEL)
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Card.TLabel', background=PANEL)
    style.configure('CardMuted.TLabel', background=PANEL, foreground=MUTED, font=('Microsoft YaHei UI', 9))
    style.configure('Heading.TLabel', background=PANEL, font=('Microsoft YaHei UI', 12, 'bold'))
    style.configure('Title.TLabel', font=('Microsoft YaHei UI', 25, 'bold'))
    style.configure('Eyebrow.TLabel', foreground=ACCENT, font=('Segoe UI', 9, 'bold'))
    style.configure('Badge.TLabel', background='#203c39', foreground=ACCENT, padding=(p(12),p(6)), font=('Segoe UI',9,'bold'))
    style.configure('TButton', background='#263747', foreground=TEXT, borderwidth=0,
                    padding=(p(14),p(9)), focuscolor=ACCENT, focusthickness=1)
    style.map('TButton', background=[('disabled','#1c2934'),('pressed','#345769'),('active','#31495b')],
              foreground=[('disabled','#657888')])
    style.configure('Go.TButton', background=ACCENT, foreground='#0d2925', font=('Microsoft YaHei UI',11,'bold'))
    style.map('Go.TButton', background=[('disabled','#30534e'),('pressed','#58bfa4'),('active','#a0efd9')],
              foreground=[('disabled','#93aaa3')])
    style.configure('TEntry', fieldbackground=FIELD, foreground=TEXT, insertcolor=ACCENT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=p(9))
    style.map('TEntry', bordercolor=[('focus',ACCENT)], fieldbackground=[('disabled','#14202a')])
    for widget in ('TCombobox','TSpinbox'):
        style.configure(widget,fieldbackground=FIELD,background='#263747',foreground=TEXT,
                        arrowcolor=ACCENT,bordercolor=BORDER,padding=p(6))
        style.map(widget,fieldbackground=[('readonly',FIELD),('disabled','#14202a')],
                  foreground=[('disabled','#718696'),('readonly',TEXT)])
    style.configure('TNotebook',background=BG,borderwidth=0)
    style.configure('TNotebook.Tab',background='#20303e',foreground=MUTED,padding=(p(14),p(9)))
    style.map('TNotebook.Tab',background=[('selected',PANEL)],foreground=[('selected',ACCENT)])
    root.option_add('*TCombobox*Listbox.background',FIELD)
    root.option_add('*TCombobox*Listbox.foreground',TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground','#284b4b')
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=p(40), borderwidth=0, font=('Microsoft YaHei UI',10))
    style.configure('Treeview.Heading', background='#20303e', foreground=MUTED, padding=(p(10),p(9)),
                    font=('Microsoft YaHei UI',9), relief='flat')
    style.map('Treeview', background=[('selected','#284b4b')], foreground=[('selected','#d8fff3')])
    style.map('Treeview.Heading', background=[('active','#263b4b')])
    style.configure('Horizontal.TProgressbar', troughcolor='#23323f', background=ACCENT,
                    borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT, thickness=p(5))
    style.configure('Vertical.TScrollbar', background='#334858', troughcolor=BG,
                    borderwidth=0, arrowsize=p(12))
    images = [tick_image(root,p(21),selected,disabled,hover) for selected,disabled,hover in
              [(False,False,False),(True,False,False),(False,True,False),(True,True,False),(False,False,True)]]
    name = 'Music.tick'
    if name not in style.element_names():
        style.element_create(name,'image',images[0],('disabled','selected',images[3]),
                             ('disabled',images[2]),('selected',images[1]),('active',images[4]),
                             border=0,sticky='')
    style.layout('Music.TCheckbutton', [('Checkbutton.padding', {'sticky':'nswe','children':[
        (name, {'side':'left','sticky':''}),('Checkbutton.focus', {'side':'left','sticky':'w','children':[
            ('Checkbutton.label', {'sticky':'nswe'})]})]})])
    style.configure('Music.TCheckbutton', background=PANEL, foreground=TEXT, padding=(0,p(4)),
                    focuscolor=ACCENT, focusthickness=1)
    style.map('Music.TCheckbutton', background=[('active',PANEL)],foreground=[('disabled','#718696')])
    root._tick_images = images  # Tk requires persistent image references.
    return style
