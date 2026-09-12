"""Gera os PNGs dos icones da tela de Ocorrencia em assets/.

Fonte: D:/icones (vermelho.png, branco.png, pause.png). O recorte e um quadrado
CENTRAL do bbox opaco (sem margem transparente, sem distorcao de aspecto) e o
resultado sai em RGBA 256x256 com a transparencia original intacta.
"""

from pathlib import Path

from PIL import Image

ORIGEM = Path("D:/icones")
DESTINO = Path("D:/Projetos/SIG Windows/assets")
LADO = 256
FONTES = {
    "mic_vermelho": "vermelho.png",
    "mic_branco": "branco.png",
    "mic_pause": "pause.png",
}


def quadrado_opaco(imagem: Image.Image) -> Image.Image:
    """Recorta o quadrado central do conteudo opaco (alpha > 10)."""
    mascara = imagem.getchannel("A").point(lambda valor: 255 if valor > 10 else 0)
    esquerda, topo, direita, base = mascara.getbbox()
    lado = max(direita - esquerda, base - topo)
    centro_x = (esquerda + direita) / 2
    centro_y = (topo + base) / 2
    return imagem.crop(
        (
            round(centro_x - lado / 2),
            round(centro_y - lado / 2),
            round(centro_x + lado / 2),
            round(centro_y + lado / 2),
        )
    )


for nome, arquivo in FONTES.items():
    with Image.open(ORIGEM / arquivo) as fonte:
        imagem = fonte.convert("RGBA")
    recorte = quadrado_opaco(imagem)
    reduzido = recorte.resize((LADO, LADO), Image.Resampling.LANCZOS)
    saida = DESTINO / f"{nome}.png"
    reduzido.save(saida, format="PNG", optimize=True)
    print(f"{saida.name}: {saida.stat().st_size / 1024:.1f} KB")
