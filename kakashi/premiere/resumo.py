"""CORRETOR - gera o resumo.md de uma sessao (portugues, legivel por gente E por IA). v0.2.0

Uso avulso (regerar depois de mexer aqui):  python resumo.py <pasta da sessao>
NUNCA apontar pra uma pasta de CORRETOR\\sessoes enquanto o Luan grava (escreve resumo.md la dentro).

Som do PC (14/10): o sessao.json traz gravar_som_pc, e cada parte pc_ok/erro_pc/pc_dispositivos/pc_eventos
(trocou/erro/aviso com t_gravacao)/pc_caiu_em/pc_reaberturas (revisao: parou sozinho e voltou no mesmo aparelho);
saidas traz pc, pc_dur, pc_pico_db, pc_seg_com_som. Sessao sem
esses campos (antes de 14/10) sai como antes.

Le sessao.json + eventos.jsonl. CONTRATO dos eventos (o painel manda; o servidor acrescenta
n, t_gravacao, quando). Todo evento tem tipo, ms (Date.now() do painel) e seq_id.
  --- desde a 0.1
  agulha       {pos, de, vel, tocando, retomada?}      pos/de em segundos da sequencia
  sequencia    {nome, projeto, zero}
  selecao      {itens:[ITEM], total}
  foto_inicial {itens:[ITEM], ms_leitura, faixas?:{V:[{nome,mudo}],A:[...],L:n}, transicoes?, entrada_saida?}
  timeline     {carga, foto, mudancas:[...], antes:ITEM|null, depois:ITEM|null, apos_pausa?, janela_ms?}
               carga = Date.now() de quando o painel carregou: o numero da foto volta a 1 se o painel
               recarregar, entao UMA leitura = (seq_id, carga, foto). Evento antigo sem carga = None.
               mudancas: adicionado | removido | inicio_mudou | fim_mudou | in_mudou | out_mudou |
                         faixa_mudou | ligado_mudou | nome_mudou | vel_mudou (0.2)
  marcador     {mudanca: novo|removido|mudou, antes, depois, alvo?: sequencia|clipe (0.2; sem alvo = sequencia),
                mestre?:{id,nome,caminho}, usos?:[{faixa,nome,pos}], janela_ms?, origem?}   MARCADOR = {id, nome, t, dur, cor, coment}
                (marcador de CLIPE: t = tempo da MIDIA; usos[].pos = onde cai na timeline)
  painel       {msg}
  --- novos na 0.2 (os que vem da foto levam carga/foto/janela_ms como o timeline)
  capacidades  {fase: inicio|fim, versao, ouvintes:{chave: "ok (...)"|"nao existe"|"erro: ..."}, existe:{...},
                leituras:{...}, campos?:{chave:{campo:valor}}, disparos?:{chave:n}}
  desempenho   {lacos:{nome:{voltas, media_ms, pico_ms, total_ms}}, capturando_s, ocupacao_media, ocupacao_pico, pico_laco, travas}
  efeito       {mudanca: colocou|tirou|param|keyframe|estado|varios, item:{faixa,nome,inicio,fim}, efeito:{idx,match,nome},
                param?:{idx,nome,antes,depois} | {idx,nome,antes_n,depois_n,tempos,valores}, efeitos?(estado), total?(varios),
                janela_ms, leitura, origem: aviso|selecionado|varredura, via?: "arrastou do painel", apos_pausa?}
  transicao    {mudanca: colocou|tirou|duracao|trocou|contagem, antes, depois (TRANS = {faixa,inicio,fim,nome,match,entre:[A,B]}), faixa?(contagem)}
  faixa        {mudanca: mute|nova|apagada|renomeou|trava_alternou, faixa, antes?, depois?, total?, renumeradas?, fonte?}
  texto        {mudanca: editou, item, antes, depois, fonte: nome_do_clipe|parametro|mogrt|nenhuma}
  legenda      {mudanca: nova|apagada|mudou, faixa, inicio, fim, antes?}
  projeto      {mudanca: importou|criou_bin|criou_sequencia|novo|apagou|renomeou|moveu|varios, item:{id,nome,tipo,bin,caminho?},
                antes?:{nome}|{bin}, conteudo?, leitura, operacao?, janela_ms}
  projeto_inicial {total, bins, sequencias, midias, ms_leitura}
  projeto_selecao {itens:[{nome,tipo}], total}          (clique no painel Projeto)
  export       {via: premiere|media_encoder, fase: fila|progresso|pronto|erro|cancelado, estado?, job?, arquivos?, progresso?, trecho?, area_trabalho?}
  desfazer_provavel {alvo: timeline|efeito, volta_a_foto?, volta_a_ms?, desfaz_fotos?, item?, efeito?, param?}
  desfazer     {fonte: evento, qual: desfez|refez, nome}  (so se um dia o Premiere tiver aviso de desfazer)
  fonte        {id, nome, caminho, pos}                    (monitor de origem)
  entrada_saida {antes:{in,out}, depois:{in,out}}
  ferramenta   {qual: navalha|limite_da_midia}
  ITEM = {faixa:"V1", tipo:"V"|"A", nome, inicio, fim, in, out, caminho, desligado, vel? (0.2: 1 = normal, -2 = 200% de tras pra frente)}
  --- revisao da 0.2 (14/10)
  timeline     + snap? (true = toda borda que mudou caiu em borda de clipe parado, agulha ou marcador da sequencia:
                 voltar ali "a mao" e plausivel), tocando? (a agulha estava tocando). O ms da foto = o 1o aviso de faixa
                 (quando houve), nao a hora da leitura.
  efeito/projeto + carga (como o timeline: o numero da leitura volta a 1 se o painel recarregar)
  projeto_inicial + projeto (nome; aparece de novo quando ele troca pra outro projeto aberto)
  export       + sucesso? (false = o Premiere avisou estado diferente de SUCCESS); trecho.fim = fim da sequencia
  --- SONDA no Premiere 26.5.2 real (14/10, SONDA-RESULTADOS.md)
  entrada_saida/export.trecho: in/out null = NAO marcado (o Premiere devolve -400000; o painel troca por null)
  efeito.item  + in, vel (o resumo converte o tempo do KEYFRAME, que vem na MIDIA, pra timeline: inicio + t - in, so a 100%)
  volume       valores em AMPLITUDE (0 dB = 0,17782794; +15 dB = 1,0) -> o resumo mostra em dB
  ITEM.in/out  com velocidade vem DIVIDIDO pela velocidade (marcador de clipe: na midia = in x vel)
  texto        fonte nome_do_clipe nao sai mais (o nome do grafico NAO acompanha o texto); fica pra sessao antiga
  --- 0.3.0 (15/10): pedacos apagados pelo Luan no painel (trilho) e Cancelar
  todo evento  + parte (numero do pedaco = parte em que caiu; o servidor poe)
  pedaco apagado: no Concluir o servidor tira os eventos dele do eventos.jsonl e reconta o t_gravacao dos outros sem
               ele (o de antes fica em t_bruto). sequencia/foto_inicial/projeto_inicial/capacidades/desempenho de
               pedaco apagado ficam, no segundo do corte, com de_pedaco_apagado: N.
  sessao.json  + pedacos_apagados [{n, dur, cortado_em (segundo da gravacao final onde ele estava), eventos_tirados,
               apagada_em, arquivos_apagados}], pausas refeitas (+ pedacos_apagados: [N] na pausa onde ele estava),
               pausas_originais; partes = so as que ficaram (t0 recontado, t0_bruto = o de antes).
  Sessao cancelada nao gera resumo (fica em sessoes\\_descartadas com "descartada": true).
Tipo desconhecido e ignorado sem erro (sessoes do 0.1 continuam gerando resumo).
"""
import bisect
import json
import math
import os
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

GAP = 0.45            # s de gravacao sem amostra = a agulha parou (o painel amostra a cada ~180 ms)
SALTO_GRANDE = 2.5    # passo maior que isso no meio de um movimento = clique/salto, nao play
EPS = 0.02            # tolerancia de igualdade de tempo na timeline (meio quadro a 24 fps)
EXATO = 0.002         # desfazer: mudanca "continua" = algum tempo andou mais que 2 ms
CONTEXTO_S = 10.0     # janela do "o que ele estava vendo" antes de cada decisao
JANELA_DESFAZER = 60.0

# ordem das linhas no mesmo segundo
O_SEQ, O_AGULHA, O_CONTEXTO, O_MUDANCA, O_EXPORT, O_DESFAZ, O_PAINEL, O_PAUSA = 0, 1, 2, 3, 4, 5, 6, 9

NOMES_EFEITO = {
    "AE.ADBE Lumetri": "Lumetri Color", "AE.ADBE Motion": "Movimento", "AE.ADBE Opacity": "Opacidade",
    "AE.ADBE Text": "Texto", "AE.ADBE Capsule": "Gráfico (MOGRT)", "AE.ADBE Gaussian Blur 2": "Desfoque gaussiano",
    "AE.ADBE AEASCCDL": "ASC CDL", "AE.ADBE Time Remapping": "Remapeamento de tempo",
}
NOMES_PARAM = {   # displayName em ingles -> portugues (o Premiere dele e PT; serve se vier em ingles)
    "Position": "Posição", "Scale": "Escala", "Scale Width": "Largura da escala", "Rotation": "Rotação",
    "Anchor Point": "Ponto de ancoragem", "Opacity": "Opacidade", "Level": "Nível", "Exposure": "Exposição",
    "Contrast": "Contraste", "Highlights": "Realces", "Shadows": "Sombras", "Whites": "Brancos", "Blacks": "Pretos",
    "Temperature": "Temperatura", "Tint": "Matiz", "Saturation": "Saturação", "Vibrance": "Vibração",
}
ROTULO_CAT = {"cor": "cor", "movimento": "movimento", "opacidade": "opacidade", "volume": "volume", "efeito": "efeito",
              "texto": "texto"}


# ------------------------------------------------------------------ formatos
def tl(s):
    """Tempo de timeline: h:mm:ss,ss"""
    if s is None:
        return "?"
    neg = s < 0
    c = int(round(abs(s) * 100))
    h, c = divmod(c, 360000)
    m, c = divmod(c, 6000)
    seg, cent = divmod(c, 100)
    return "%s%d:%02d:%02d,%02d" % ("-" if neg else "", h, m, seg, cent)


def rec(t):
    """Tempo de gravacao: [mm:ss.s]"""
    d = int(round(max(0.0, t or 0.0) * 10))
    m, d = divmod(d, 600)
    return "[%02d:%02d.%d]" % (m, d // 10, d % 10)


def num(x, casas=1, sinal=False):
    s = ("%+." if sinal else "%.") + str(casas) + "f"
    return (s % x).replace(".", ",")


def dur(x):
    x = abs(x or 0.0)
    if x < 90:
        return num(x) + " s"
    m, s = divmod(int(round(x)), 60)
    if m < 60:
        return "%d min %02d s" % (m, s)
    h, m = divmod(m, 60)
    return "%d h %02d min" % (h, m)


def base(p):
    return os.path.basename(str(p).replace("\\", "/")) if p else ""


def mesma_midia(a, b):
    if a.get("caminho") or b.get("caminho"):
        return (a.get("caminho") or "").lower() == (b.get("caminho") or "").lower()
    return a.get("nome") == b.get("nome")


def perto(a, b, tol=EPS):
    return a is not None and b is not None and abs(a - b) <= tol


def ordem_faixa(f):
    f = f or "?"
    return ({"V": 0, "A": 1, "L": 2}.get(f[:1], 3), int(f[1:]) if f[1:].isdigit() else 0)


def faixas_txt(fs):
    fs = sorted(set(x for x in fs if x), key=ordem_faixa)
    return "+".join(fs)


def item_txt(it, faixas=None):
    return "%s [%s %s-%s]" % (it.get("nome") or "?", faixas or it.get("faixa") or "?", tl(it.get("inicio")), tl(it.get("fim")))


def valor_txt(v):
    if v is None:
        return "?"
    if isinstance(v, bool):
        return "ligado" if v else "desligado"
    if isinstance(v, (int, float)):
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        s = ("%.3f" % v).rstrip("0").rstrip(".")
        return s.replace(".", ",")
    if isinstance(v, str):
        return "'%s'" % v
    if isinstance(v, list):
        return "(" + "; ".join(valor_txt(x) for x in v) + ")"
    if isinstance(v, dict) and "texto" in v:
        return "'%s'" % v.get("texto")
    return json.dumps(v, ensure_ascii=False)


AMP_0DB = 10 ** (-15 / 20.0)      # 0,17782794: o 0 dB do volume do Premiere em amplitude (SONDA 14/10, passo 3)


def eh_volume(ef):
    """componente de volume (Internal Volume Stereo / Internal Channel Volume Stereo / ...)"""
    ef = ef or {}
    return "volume" in ((ef.get("match") or "") + " " + (ef.get("nome") or "")).lower()


def db_volume(v):
    """amplitude do Premiere -> dB como o Controle de Efeitos mostra. MEDIDO na SONDA (14/10): o Nivel padrao (0 dB)
    vem 0,17782794 = 10^(-15/20); o teto do slider (+15 dB) e 1,0. Entao dB = 20*log10(v) + 15."""
    return 20 * math.log10(v) + 15 if v > 0 else None


def valor_param_txt(ef, v):
    """valor de parametro pra gente ler: volume em dB (vem em amplitude), o resto como valor_txt"""
    if eh_volume(ef) and isinstance(v, (int, float)) and not isinstance(v, bool):
        d = db_volume(v)
        return "-∞ dB" if d is None else num(round(d, 1) + 0.0, 1) + " dB"     # + 0.0: nada de "-0,0"
    return valor_txt(v)


def tempos_keyframe(it, ef, p):
    """tempos dos KEYFRAMES pra gente ler. O tempo vem na MIDIA, nao na timeline (SONDA 14/10, passo 3: keyframes de
    Escala em 10,933 e 14,833 num clipe que ocupa 21,033-36,6 da timeline com in 5,467 / out 21,033 - dentro do trecho
    da midia, fora do da timeline). Converte pra timeline como o marcador de clipe: inicio + (t - in), so com
    velocidade 100% (com outra velocidade a sonda nao mediu o keyframe) e so se TODOS caem dentro do trecho usado;
    senao mostra so o tempo da midia. Evento antigo (sem item.in) = so o tempo da midia."""
    tempos = list(p.get("tempos") or [])[:6]
    if not tempos:
        return ""
    valores = list(p.get("valores") or [])[:6]
    vtxt = [valor_param_txt(ef, v) for v in valores] + ["?"] * max(0, len(tempos) - len(valores))
    it = it or {}
    ini, fim, inn, vel = it.get("inicio"), it.get("fim"), it.get("in"), it.get("vel")
    if ini is not None and inn is not None and (vel is None or abs(vel - 1) < 0.0005):
        dura = (fim - ini) if fim is not None else None
        if all(t >= inn - 0.05 and (dura is None or t <= inn + dura + 0.05) for t in tempos):
            return " (na timeline: %s · na mídia: %s)" % (
                ", ".join("%s = %s" % (tl(ini + t - inn), v) for t, v in zip(tempos, vtxt)), ", ".join(tl(t) for t in tempos))
    return " (tempo na mídia, não na timeline: %s)" % ", ".join("%s = %s" % (tl(t), v) for t, v in zip(tempos, vtxt))


def pct(v):
    """velocidade do clipe: getSpeed() devolve FATOR (1 = 100%) - confirmado na SONDA 14/10 (200% veio 2); se
    vier acima de 20 assume que ja e porcentagem (rede)"""
    if v is None:
        return "?"
    a = abs(v)
    p = a * 100 if a <= 20 else a
    s = ("%.1f" % p).rstrip("0").rstrip(".").replace(".", ",") + "%"
    return s + (" de trás pra frente" if v < 0 else "")


def nome_efeito(ef):
    ef = ef or {}
    m = ef.get("match") or ""
    return ef.get("nome") or NOMES_EFEITO.get(m) or (m.replace("AE.ADBE ", "") if m else "?")


def nome_param(p):
    n = (p or {}).get("nome") or "parâmetro %s" % (p or {}).get("idx")
    return NOMES_PARAM.get(n, n)


def cat_efeito(e):
    m = ((e.get("efeito") or {}).get("match") or "").lower()
    n = ((e.get("efeito") or {}).get("nome") or "").lower()
    f = ((e.get("item") or {}).get("faixa") or "")
    if "lumetri" in m or "color" in m or "cdl" in m or "cor" in n:
        return "cor"
    if "motion" in m or "movimento" in n:
        return "movimento"
    if "opacity" in m or "opacidade" in n:
        return "opacidade"
    if "text" in m or "capsule" in m:
        return "texto"
    if f.startswith("A"):
        return "volume" if ("volume" in m or "volume" in n or "level" in m or not m) else "efeito"
    return "efeito"


# ------------------------------------------------------------------ leitura
def ler(pasta):
    pasta = Path(pasta)
    meta = json.loads((pasta / "sessao.json").read_text(encoding="utf-8"))
    eventos = []
    arq = pasta / "eventos.jsonl"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
            linha = linha.strip()
            if not linha:
                continue
            try:
                eventos.append(json.loads(linha))
            except Exception:
                continue        # linha cortada por queda: pula
    for e in eventos:
        e["t"] = float(e.get("t_gravacao") or 0.0)
    eventos.sort(key=lambda e: (e.get("ms") or 0, e.get("n") or 0))
    return meta, eventos


# ------------------------------------------------------------------ agulha
def _mediana(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def eh_play(evs):
    """v0.2 (defeito B): play = velocidade ESTAVEL. Arrastar a agulha da velocidades soltas
    (1,9 / 2,3 / 6,3 / 0,7) e virava "play 2,3x". Agora: >= 3 amostras e >= 60% delas a ate 30%
    da velocidade mediana (entre 0,5x e 8,5x). Nao depende da bandeira `tocando` do painel."""
    if len(evs) < 3:
        return False, None
    vels = [e.get("vel") for e in evs[1:] if e.get("vel") is not None]
    if len(vels) < 2:
        return False, None
    faixa = [v for v in vels if 0.5 <= abs(v) <= 8.5]
    if not faixa:
        return False, None
    med = _mediana(faixa)
    estaveis = [v for v in vels if abs(v - med) <= 0.30 * abs(med)]
    if len(estaveis) < 0.6 * len(vels):
        return False, None
    # fora de ~1x (J/L rapido ou arrasto constante): so com >= 5 amostras (~0,9 s). Sessao 14:42 tinha
    # um arrasto de 0,36 s a 4,7x que virava "play 4,7x de tras pra frente"
    if not (0.75 <= abs(med) <= 1.3) and len(evs) < 5:
        return False, None
    return True, med


def movimentos(agulhas):
    """Agrupa amostras de agulha em gestos: play | salto | passo | arrasto."""
    movs, cur = [], None

    def novo(e, origem=None):
        de = e.get("de")
        return {"evs": [e], "seq_id": e.get("seq_id"), "ini": de if (origem is None and de is not None) else (origem if origem is not None else e["pos"])}

    for e in agulhas:
        if e.get("pos") is None:
            continue
        ultimo = cur["evs"][-1] if cur else None
        continua = (cur is not None and not e.get("retomada") and e.get("seq_id") == cur["seq_id"]
                    and e["t"] - ultimo["t"] <= GAP)
        if continua and cur.get("fechado") and len(cur["evs"]) == 1 and cur["evs"][0] is ultimo:
            # depois de um salto, o gesto colado comeca no destino do salto
            cur = {"evs": [e], "seq_id": e.get("seq_id"), "ini": ultimo["pos"]}
            movs.append(cur)
            continue
        if continua and abs(e["pos"] - ultimo["pos"]) > SALTO_GRANDE and not e.get("tocando"):
            # clique no meio de um play: o salto vira gesto proprio, o play seguinte comeca do destino
            movs.append({"evs": [e], "seq_id": e.get("seq_id"), "ini": ultimo["pos"], "fechado": True})
            cur = None
            continue
        if continua and not cur.get("fechado"):
            cur["evs"].append(e)
        elif (e.get("de") is not None and not e.get("tocando") and not e.get("retomada")
              and abs(e["pos"] - e["de"]) >= 0.5):
            # 1a amostra de um gesto ja longe de onde estava = clique/salto; o que vier colado comeca do destino
            movs.append({"evs": [e], "seq_id": e.get("seq_id"), "ini": e["de"], "fechado": True})
            cur = movs[-1]
        else:
            cur = novo(e)
            movs.append(cur)
    for m in movs:
        evs = m["evs"]
        m["fim"] = evs[-1]["pos"]
        m["t_ini"] = evs[0]["t"]
        m["t_fim"] = evs[-1]["t"]
        m["lo"] = min([m["ini"]] + [e["pos"] for e in evs])
        m["hi"] = max([m["ini"]] + [e["pos"] for e in evs])
        play, vel = eh_play(evs)
        if play:
            m["tipo"] = "play"
            m["vel"] = vel
            # duracao do play: do instante da amostra anterior a 1a ate a ultima
            passo = (evs[1]["t"] - evs[0]["t"]) if len(evs) > 1 else 0.18
            m["dur"] = (m["t_fim"] - m["t_ini"]) + min(passo, GAP)
        elif len(evs) == 1 and (evs[0].get("retomada") or abs(m["fim"] - m["ini"]) < 0.0005):
            m["tipo"] = "posicao"
        elif len(evs) == 1:
            m["tipo"] = "salto" if abs(m["fim"] - m["ini"]) >= 0.5 else "passo"
        else:
            m["tipo"] = "arrasto"
    # quadro a quadro: passos curtos seguidos viram um gesto so
    out = []
    for m in movs:
        ant = out[-1] if out else None
        if (m["tipo"] == "passo" and ant is not None and ant["tipo"] in ("passo", "passos")
                and m["seq_id"] == ant["seq_id"] and m["t_ini"] - ant["t_fim"] <= 2.5):
            ant["tipo"] = "passos"
            ant["n"] = ant.get("n", 1) + 1
            ant["fim"] = m["fim"]
            ant["t_fim"] = m["t_fim"]
            ant["lo"], ant["hi"] = min(ant["lo"], m["lo"]), max(ant["hi"], m["hi"])
            continue
        out.append(m)
    # salto seguido de play que comeca no destino = "foi pra la e assistiu"
    final = []
    for m in out:
        ant = final[-1] if final else None
        if (m["tipo"] == "play" and ant is not None and ant["tipo"] == "salto" and m["seq_id"] == ant["seq_id"]
                and m["t_ini"] - ant["t_fim"] <= 3.0 and abs(m["ini"] - ant["fim"]) <= 0.4):
            m["via_salto"] = ant["ini"]
            m["t_ini"] = ant["t_ini"]
            final[-1] = m
            continue
        final.append(m)
    return final


def intersecao(a, b, intervalos):
    tot = 0.0
    for x, y in intervalos:
        lo, hi = max(a, x), min(b, y)
        if hi > lo:
            tot += hi - lo
    return tot


def descrever_movimentos(movs):
    """Devolve [(t, texto, m)] e marca revisoes (m['revisao']=True)."""
    vistos = {}         # seq_id -> [(a,b)]
    ultima_pos = {}
    linhas = []
    for m in movs:
        sid = m["seq_id"]
        vis = vistos.setdefault(sid, [])
        antes = ultima_pos.get(sid)
        if m["tipo"] == "play":
            a, b = min(m["ini"], m["fim"]), max(m["ini"], m["fim"])
            vel = m.get("vel") or 1.0
            modo = "play" if 0.75 <= abs(vel) <= 1.3 else "play %sx" % num(abs(vel), 1).rstrip("0").rstrip(",")
            if vel < 0:
                modo += " de trás pra frente"
            ja = intersecao(a, b, vis)
            origem = m.get("via_salto", antes)
            if b - a > 0.05 and ja >= 0.5 * (b - a):
                m["revisao"] = True
                if origem is not None and origem > m["ini"] and origem - m["ini"] <= 60:
                    txt = "voltou %s e reviu de %s a %s (%s, %s)" % (dur(origem - m["ini"]), tl(m["ini"]), tl(m["fim"]), modo, dur(m["dur"]))
                else:
                    txt = "reviu de %s a %s (%s, %s) - já tinha assistido esse trecho" % (tl(m["ini"]), tl(m["fim"]), modo, dur(m["dur"]))
            else:
                txt = "assistiu de %s a %s (%s, %s)" % (tl(m["ini"]), tl(m["fim"]), modo, dur(m["dur"]))
                if m.get("via_salto") is not None:
                    txt = "pulou de %s pra %s e %s" % (tl(m["via_salto"]), tl(m["ini"]), txt)
            vis.append((a, b))
        elif m["tipo"] == "posicao":
            ret = m["evs"][0].get("retomada")
            txt = "agulha em %s%s" % (tl(m["fim"]), " (ao retomar)" if ret else "")
        elif m["tipo"] == "salto":
            d = m["fim"] - m["ini"]
            verbo = "pulou" if d > 0 else "voltou"
            txt = "%s de %s pra %s (%s)" % (verbo, tl(m["ini"]), tl(m["fim"]), num(d, 2, True) + " s")
        elif m["tipo"] == "passo":
            txt = "ajustou a agulha de %s pra %s (%s)" % (tl(m["ini"]), tl(m["fim"]), num(m["fim"] - m["ini"], 2, True) + " s")
        elif m["tipo"] == "passos":
            txt = "andou quadro a quadro de %s a %s (%d toques, %s)" % (tl(m["ini"]), tl(m["fim"]), m.get("n", 1), num(m["fim"] - m["ini"], 2, True) + " s")
        else:
            txt = "arrastou a agulha de %s até %s (passou por %s-%s, %s)" % (
                tl(m["ini"]), tl(m["fim"]), tl(m["lo"]), tl(m["hi"]), dur(m["t_fim"] - m["t_ini"]))
        ultima_pos[sid] = m["fim"]
        m["texto"] = txt
        linhas.append((m["t_ini"], txt, m))
    return linhas


# ------------------------------------------------------------------ selecao
def agrupar_vinculados(itens):
    """Video+audio vinculados (mesmo nome e tempos) viram uma entrada 'V1+A1'."""
    grupos = {}
    ordem = []
    for it in itens or []:
        k = (it.get("nome"), round(it.get("inicio") or 0, 2), round(it.get("fim") or 0, 2))
        if k not in grupos:
            grupos[k] = []
            ordem.append(k)
        grupos[k].append(it)
    return [(grupos[k][0], faixas_txt([i.get("faixa") or "?" for i in grupos[k]])) for k in ordem]


def texto_selecao(e):
    itens = e.get("itens") or []
    if not itens:
        return "tirou a seleção"
    g = agrupar_vinculados(itens)
    total = e.get("total") or len(itens)
    if len(g) == 1:
        return "selecionou " + item_txt(g[0][0], g[0][1])
    lista = "; ".join(item_txt(it, f) for it, f in g[:5])
    extra = " e mais %d" % (len(g) - 5) if len(g) > 5 else ""
    if total > len(itens):
        extra += " (%d itens no total; só os primeiros vieram)" % total
    return "selecionou %d itens: %s%s" % (len(g), lista, extra)


# ------------------------------------------------------------------ timeline
class Frase:
    def __init__(self, cat, chave, faixa, fmt, pos=None, decisao=True, refs=None, so_nome=False):
        self.cat, self.chave, self.fmt, self.pos, self.decisao = cat, chave, fmt, pos, decisao
        self.faixas = [faixa] if faixa else []
        self.refs = list(refs or [])
        self.so_nome = so_nome


def juntar_frases(frases):
    out, idx = [], {}
    for f in frases:
        if f.chave in idx:
            idx[f.chave].faixas.extend(f.faixas)
            idx[f.chave].refs.extend(f.refs)
        else:
            idx[f.chave] = f
            out.append(f)
    return out


def interpretar(grupo):
    """grupo = eventos 'timeline' de UMA leitura (mesma foto). Devolve [Frase].
    Cada Frase guarda em .refs os eventos (objetos) que a formaram (pra marcar 'desfeita')."""
    pares, adds, rems = [], [], []
    dono = {}
    for e in grupo:
        mud = e.get("mudancas") or []
        if "adicionado" in mud and e.get("depois"):
            adds.append(e["depois"])
            dono[id(e["depois"])] = e
        elif "removido" in mud and e.get("antes"):
            rems.append(e["antes"])
            dono[id(e["antes"])] = e
        elif e.get("antes") and e.get("depois"):
            pares.append(e)
    frases = []
    # 1) razor: um item encurtou o fim e nasceu outro, mesma midia, colado, ate o fim antigo
    for p in list(pares):
        a, d = p["antes"], p["depois"]
        if not (perto(a.get("inicio"), d.get("inicio")) and d.get("fim", 0) < a.get("fim", 0) - EPS and a.get("faixa") == d.get("faixa")):
            continue
        for n in adds:
            if (n.get("faixa") == d.get("faixa") and mesma_midia(n, d) and perto(n.get("inicio"), d.get("fim"))
                    and perto(n.get("fim"), a.get("fim"))):
                t = d["fim"]
                nome = d.get("nome") or "?"
                frases.append(Frase("corte", ("corte", nome, round(t, 2)), d.get("faixa"),
                                    lambda fx, nome=nome, t=t: "cortou (razor) %s em %s [%s]" % (nome, tl(t), fx), pos=t,
                                    refs=[p, dono.get(id(n))]))
                pares.remove(p)
                adds.remove(n)
                break
    # 2) apagado + colocado com a mesma midia e mesmo in/out = moveu (arrastou/recortou-colou)
    for r in list(rems):
        for n in adds:
            if mesma_midia(r, n) and perto(r.get("in"), n.get("in")) and perto(r.get("out"), n.get("out")):
                pares.append({"antes": r, "depois": n, "mudancas": ["faixa_mudou" if r.get("faixa") != n.get("faixa") else "inicio_mudou"],
                              "_refs": [dono.get(id(r)), dono.get(id(n))]})
                rems.remove(r)
                adds.remove(n)
                break
    deslocados = {}
    for p in pares:
        a, d = p["antes"], p["depois"]
        refs = p.get("_refs") or [p]
        nome = d.get("nome") or a.get("nome") or "?"
        di = (d.get("inicio") or 0) - (a.get("inicio") or 0)
        df = (d.get("fim") or 0) - (a.get("fim") or 0)
        din = (d.get("in") or 0) - (a.get("in") or 0)
        dout = (d.get("out") or 0) - (a.get("out") or 0)
        z = lambda x: abs(x) <= EPS
        vel_a, vel_d = a.get("vel"), d.get("vel")
        mudou_vel = vel_a is not None and vel_d is not None and abs(vel_a - vel_d) > 0.0005
        if bool(a.get("desligado")) != bool(d.get("desligado")):
            verbo = "desligou" if d.get("desligado") else "religou"
            frases.append(Frase("ligado", ("ligado", nome, verbo, round(d.get("inicio") or 0, 2)), d.get("faixa"),
                                lambda fx, v=verbo, it=d: "%s %s" % (v, item_txt(it, fx)), pos=d.get("inicio"), refs=refs))
            if z(di) and z(df) and z(din) and z(dout) and a.get("faixa") == d.get("faixa") and not mudou_vel:
                continue
        if mudou_vel:
            # velocidade (Ctrl+R): sem este ramo o fim que andou viraria "trim" (defeito D)
            extra = ""
            if not z(df):
                extra = " (fim %s -> %s)" % (tl(a.get("fim")), tl(d.get("fim")))
            elif not z(di):
                extra = " (início %s -> %s)" % (tl(a.get("inicio")), tl(d.get("inicio")))
            frases.append(Frase("velocidade", ("vel", nome, round(a.get("inicio") or 0, 2), vel_d), d.get("faixa"),
                                lambda fx, nome=nome, va=vel_a, vd=vel_d, extra=extra: "VELOCIDADE: %s [%s] %s -> %s%s" % (nome, fx, pct(va), pct(vd), extra),
                                pos=d.get("inicio"), refs=refs))
            continue
        if a.get("faixa") != d.get("faixa"):
            extra = (" e %s no tempo (%s -> %s)" % (num(di, 2, True) + " s", tl(a.get("inicio")), tl(d.get("inicio")))) if not z(di) else ""
            par = "%s->%s" % (a.get("faixa"), d.get("faixa"))
            frases.append(Frase("moveu", ("faixa", nome, round(di, 2), round(a.get("inicio") or 0, 2)), par,
                                lambda fx, nome=nome, extra=extra: "moveu %s de faixa (%s)%s" % (nome, fx.replace("+", ", "), extra),
                                pos=d.get("inicio"), refs=refs))
            continue
        if z(din) and z(dout) and not z(di) and z(di - df):
            deslocados.setdefault(round(di, 2), []).append(p)
            continue
        if z(di) and z(din) and not z(df):
            verbo = "encurtou" if df < 0 else "alongou"
            frases.append(Frase("trim", ("fim", nome, round(df, 2), round(a.get("fim") or 0, 2)), d.get("faixa"),
                                lambda fx, v=verbo, nome=nome, a=a, d=d, df=df: "%s o fim de %s [%s] de %s pra %s (%s)" % (
                                    v, nome, fx, tl(a.get("fim")), tl(d.get("fim")), num(df, 2, True) + " s"), pos=d.get("fim"), refs=refs))
            continue
        if z(df) and not z(di) and z(di - din):
            verbo = "encurtou" if di > 0 else "alongou"
            frases.append(Frase("trim", ("ini", nome, round(di, 2), round(a.get("inicio") or 0, 2)), d.get("faixa"),
                                lambda fx, v=verbo, nome=nome, a=a, d=d, di=di: "%s o início de %s [%s] de %s pra %s (%s)" % (
                                    v, nome, fx, tl(a.get("inicio")), tl(d.get("inicio")), num(di, 2, True) + " s"), pos=d.get("inicio"), refs=refs))
            continue
        if z(di) and not z(din) and z(df + din):
            verbo = "cortou o começo de" if din > 0 else "devolveu o começo de"
            frases.append(Frase("trim", ("ripini", nome, round(din, 2), round(a.get("inicio") or 0, 2)), d.get("faixa"),
                                lambda fx, v=verbo, nome=nome, a=a, d=d, din=din: "%s %s [%s] com ripple: %s (in %s -> %s; o resto andou junto)" % (
                                    v, nome, fx, dur(din), tl(a.get("in")), tl(d.get("in"))), pos=d.get("inicio"), refs=refs))
            continue
        if z(di) and z(df) and not z(din) and z(din - dout):
            frases.append(Frase("slip", ("slip", nome, round(din, 2), round(a.get("inicio") or 0, 2)), d.get("faixa"),
                                lambda fx, nome=nome, d=d, din=din: "deslizou o conteúdo (slip) de %s em %s (in %s)" % (
                                    item_txt(d, fx), num(din, 2, True) + " s", tl(d.get("in"))), pos=d.get("inicio"), refs=refs))
            continue
        partes = []
        for campo, rot in (("inicio", "início"), ("fim", "fim"), ("in", "in"), ("out", "out")):
            if not z((d.get(campo) or 0) - (a.get(campo) or 0)):
                partes.append("%s %s -> %s" % (rot, tl(a.get(campo)), tl(d.get(campo))))
        so_nome = False
        if a.get("nome") != d.get("nome"):
            so_nome = not partes
            partes.append("nome '%s' -> '%s'" % (a.get("nome"), d.get("nome")))
        if not partes:
            # defeito D: mudanca sem frase propria nao some calada
            difs = []
            for campo in sorted(set(a.keys()) | set(d.keys())):
                if campo in ("faixa", "tipo") or a.get(campo) == d.get(campo):
                    continue
                difs.append("%s %s -> %s" % (campo, valor_txt(a.get(campo)), valor_txt(d.get(campo))))
            partes = difs or ["(%s)" % ", ".join(p.get("mudancas") or ["?"])]
        frases.append(Frase("outro", ("outro", nome, tuple(partes), round(d.get("inicio") or 0, 2)), d.get("faixa"),
                            lambda fx, nome=nome, partes=partes: "mudou %s [%s]: %s" % (nome, fx, "; ".join(partes)), pos=d.get("inicio"),
                            refs=refs, so_nome=so_nome))
    outros = bool(rems or adds or frases)
    for r in rems:
        frases.append(Frase("apagou", ("apagou", r.get("nome"), round(r.get("inicio") or 0, 2), round(r.get("fim") or 0, 2)), r.get("faixa"),
                            lambda fx, r=r: "apagou %s (%s)" % (item_txt(r, fx), dur((r.get("fim") or 0) - (r.get("inicio") or 0))),
                            pos=r.get("inicio"), refs=[dono.get(id(r))]))
    for n in adds:
        frases.append(Frase("novo", ("novo", n.get("nome"), round(n.get("inicio") or 0, 2), round(n.get("fim") or 0, 2)), n.get("faixa"),
                            lambda fx, n=n: "colocou novo: %s (%s) em %s %s-%s, in %s out %s" % (
                                n.get("nome"), base(n.get("caminho")) or "sem arquivo", fx, tl(n.get("inicio")), tl(n.get("fim")),
                                tl(n.get("in")), tl(n.get("out"))), pos=n.get("inicio"), refs=[dono.get(id(n))]))
    # o ripple ("empurrados pela mudanca acima") vem DEPOIS da mudanca que empurrou
    for delta, ps in sorted(deslocados.items()):
        fx = [p["depois"].get("faixa") for p in ps]
        if outros or len(ps) > 2:
            def fmt(_f, delta=delta, ps=ps, fx=fx):
                return "%d itens andaram %s (%s) - empurrados pela mudança acima (ripple), a partir de %s" % (
                    len(ps), num(delta, 2, True) + " s", faixas_txt(fx), tl(min(p["antes"].get("inicio") or 0 for p in ps)))
            frases.append(Frase("ripple", ("ripple", delta), None, fmt, pos=min(p["depois"].get("inicio") or 0 for p in ps), decisao=not outros,
                                refs=[r for p in ps for r in (p.get("_refs") or [p])]))
        else:
            for p in ps:
                a, d = p["antes"], p["depois"]
                frases.append(Frase("moveu", ("tempo", d.get("nome"), delta, round(a.get("inicio") or 0, 2)), d.get("faixa"),
                                    lambda fx, a=a, d=d, delta=delta: "moveu %s [%s] de %s pra %s (%s)" % (
                                        d.get("nome"), fx, tl(a.get("inicio")), tl(d.get("inicio")), num(delta, 2, True) + " s"),
                                    pos=d.get("inicio"), refs=p.get("_refs") or [p]))
    for f in frases:
        f.refs = [r for r in f.refs if r is not None]
    return juntar_frases(frases)


# ------------------------------------------------------------------ marcadores
def usos_txt(usos):
    por = {}
    ordem = []
    for u in usos or []:
        k = round(u.get("pos") or 0, 2)
        if k not in por:
            por[k] = []
            ordem.append(k)
        por[k].append(u.get("faixa"))
    return [(k, faixas_txt(por[k])) for k in ordem]


def texto_marcador(e):
    m = e.get("depois") or e.get("antes") or {}
    nome = m.get("nome") or "(sem nome)"
    com = (" - comentário: \"%s\"" % m.get("coment")) if m.get("coment") else ""
    mud = e.get("mudanca")
    if e.get("alvo") == "clipe":
        mestre = e.get("mestre") or {}
        nm = mestre.get("nome") or base(mestre.get("caminho")) or "?"
        rotulo = (" '%s'" % m.get("nome")) if m.get("nome") else ""
        us = usos_txt(e.get("usos"))
        if mud == "novo":
            if us:
                lugares = "; ".join("[%s], cai em %s da timeline" % (fx, tl(pos)) for pos, fx in us)
                return "marcador novo%s no clipe '%s' %s (%s da mídia)%s" % (rotulo, nm, lugares, tl(m.get("t")), com)
            return ("marcador novo%s no clipe-mestre '%s' em %s da mídia (fora do trecho usado na timeline; talvez no monitor de origem)%s"
                    % (rotulo, nm, tl(m.get("t")), com))
        if mud == "removido":
            onde = (" (caía em %s da timeline)" % tl(us[0][0])) if us else ""
            return "apagou o marcador%s do clipe '%s' (%s da mídia)%s" % (rotulo, nm, tl(m.get("t")), onde)
        a, d = e.get("antes") or {}, e.get("depois") or {}
        return "mudou o marcador%s do clipe '%s': %s" % (rotulo, nm, _partes_marcador(a, d))
    if mud == "novo":
        return "marcador novo '%s' em %s%s" % (nome, tl(m.get("t")), com)
    if mud == "removido":
        return "apagou o marcador '%s' em %s" % (nome, tl(m.get("t")))
    a, d = e.get("antes") or {}, e.get("depois") or {}
    return "mudou o marcador '%s': %s" % (nome, _partes_marcador(a, d))


def _partes_marcador(a, d):
    partes = []
    if a.get("nome") != d.get("nome"):
        partes.append("nome '%s' -> '%s'" % (a.get("nome"), d.get("nome")))
    if not perto(a.get("t"), d.get("t")):
        partes.append("de %s pra %s" % (tl(a.get("t")), tl(d.get("t"))))
    if a.get("coment") != d.get("coment"):
        partes.append("comentário: \"%s\"" % (d.get("coment") or ""))
    if not perto(a.get("dur"), d.get("dur")):
        partes.append("duração %s -> %s" % (dur(a.get("dur")), dur(d.get("dur"))))
    if a.get("cor") != d.get("cor"):
        partes.append("cor %s -> %s" % (a.get("cor"), d.get("cor")))
    return "; ".join(partes) or "detalhe"


# ------------------------------------------------------------------ textos dos tipos novos
def item_curto(it):
    it = it or {}
    return "%s [%s]" % (it.get("nome") or "?", it.get("faixa") or "?")


def texto_transicao(e):
    m = e.get("mudanca")
    if m == "contagem":
        return "%s: %s -> %s transição(ões) (o Premiere não deixou ler os detalhes)" % (e.get("faixa"), e.get("antes"), e.get("depois"))
    a, d = e.get("antes") or {}, e.get("depois") or {}
    x = d or a

    def entre(t):
        en = t.get("entre") or [None, None]
        if en[0] and en[1]:
            return "entre %s e %s" % (en[0], en[1])
        if en[1]:
            return "no começo de %s" % en[1]
        if en[0]:
            return "no fim de %s" % en[0]
        return "em %s" % tl(t.get("inicio"))

    def nome(t):
        return t.get("nome") or (t.get("match") or "transição").replace("AE.ADBE ", "")

    def duracao(t):
        if t.get("inicio") is None or t.get("fim") is None:
            return "?"
        return dur(t["fim"] - t["inicio"])
    if m == "colocou":
        return "colocou %s (%s) %s [%s] em %s" % (nome(d), duracao(d), entre(d), d.get("faixa"), tl(d.get("inicio")))
    if m == "tirou":
        return "tirou %s (%s) %s [%s]" % (nome(a), duracao(a), entre(a), a.get("faixa"))
    if m == "duracao":
        return "%s %s [%s] passou de %s pra %s" % (nome(d), entre(d), d.get("faixa"), duracao(a), duracao(d))
    if m == "trocou":
        return "trocou %s por %s %s [%s]" % (nome(a), nome(d), entre(d), d.get("faixa"))
    return "%s %s [%s]" % (m, nome(x), x.get("faixa"))


def texto_faixa(e):
    m, f = e.get("mudanca"), e.get("faixa") or "?"
    if m == "mute":
        if f.startswith("V"):
            return ("escondeu %s (olhinho)" if e.get("depois") else "mostrou %s de novo (olhinho)") % f
        return ("mutou %s" if e.get("depois") else "desmutou %s") % f
    if m == "nova":
        ren = e.get("renumeradas") or []
        extra = " (as de cima subiram um número: %s)" % ", ".join(ren) if ren else ""
        return "criou a faixa %s%s" % (f, extra)
    if m == "apagada":
        ren = e.get("renumeradas") or []
        extra = " (as de cima desceram: %s)" % ", ".join(ren) if ren else ""
        return "apagou a faixa %s%s" % (f, extra)
    if m == "renomeou":
        return "renomeou a faixa %s: '%s' -> '%s'" % (f, e.get("antes") or "", e.get("depois") or "")
    if m == "trava_alternou":
        return "mexeu no cadeado de %s (travou ou destravou: ver na tela)" % f
    return "%s %s" % (m, f)


def texto_texto(e):
    it = e.get("item") or {}
    onde = "[%s] %s" % (it.get("faixa") or "?", tl(it.get("inicio")))
    fonte = e.get("fonte")
    if e.get("depois") in (None, "") and e.get("antes") in (None, ""):
        return "mexeu no texto em %s (o Premiere não deixa ler o conteúdo: ver na tela)" % onde
    rot = {"nome_do_clipe": " (pelo nome do clipe)", "parametro": "", "mogrt": " (MOGRT)"}.get(fonte, "")
    return "editou o texto em %s: '%s' -> '%s'%s" % (onde, e.get("antes") or "", e.get("depois") or "", rot)


def texto_legenda(e):
    m = e.get("mudanca")
    trecho = "%s-%s" % (tl(e.get("inicio")), tl(e.get("fim")))
    if m == "nova":
        return "criou legenda em %s [%s] (texto só na tela)" % (trecho, e.get("faixa"))
    if m == "apagada":
        return "apagou a legenda de %s [%s]" % (trecho, e.get("faixa"))
    a = e.get("antes") or {}
    return "mudou o tempo da legenda [%s]: %s-%s -> %s" % (e.get("faixa"), tl(a.get("inicio")), tl(a.get("fim")), trecho)


TIPO_PROJ = {"bin": "o bin", "sequencia": "a sequência", "midia": "", "outro": ""}


def texto_projeto_um(e):
    m = e.get("mudanca")
    it = e.get("item") or {}
    nome = it.get("nome") or "?"
    art = TIPO_PROJ.get(it.get("tipo"), "")
    quem = ("%s '%s'" % (art, nome)) if art else nome
    if m == "criou_bin":
        dentro = ""
        if e.get("conteudo"):
            amostra = ", ".join((e.get("filhos") or [])[:5])
            dentro = " com %d itens dentro%s" % (e["conteudo"], (" (" + amostra + ("..." if e["conteudo"] > 5 else "") + ")") if amostra else "")
        return "criou o bin '%s'%s%s" % (nome, "" if it.get("bin") in (None, "(raiz)") else " dentro de '%s'" % it.get("bin"), dentro)
    if m == "criou_sequencia":
        return "criou a sequência '%s'" % nome
    if m == "novo":
        return "apareceu no projeto: %s (bin '%s')" % (nome, it.get("bin"))
    if m == "apagou":
        extra = " (com %d itens dentro)" % e["conteudo"] if e.get("conteudo") else ""
        return "apagou %s%s" % (quem, extra)
    if m == "renomeou":
        return "renomeou %s'%s' pra '%s'" % ((art + " ") if art else "", (e.get("antes") or {}).get("nome"), nome)
    if m == "moveu":
        return "moveu %s de '%s' pra '%s'" % (quem, (e.get("antes") or {}).get("bin"), it.get("bin"))
    if m == "varios":
        return "%d mudanças de uma vez no projeto" % (e.get("total") or 0)
    return "%s %s" % (m, nome)


def io_txt(x):
    """entrada/saida da sequencia. None = nao marcada (o painel 0.2 manda null: o Premiere 26.5.2 devolve -400000
    sem nada marcado - SONDA 14/10). Sessao antiga pode trazer o -400000 cru: negativo tambem e 'nao marcada'."""
    x = x or {}
    i = x.get("in") if x.get("in") is not None and x.get("in") >= 0 else None
    o = x.get("out") if x.get("out") is not None and x.get("out") >= 0 else None
    if i is None and o is None:
        return "nada marcado"
    if i is None:
        return "saída em %s (sem entrada)" % tl(o)
    if o is None:
        return "entrada em %s (sem saída)" % tl(i)
    return "%s-%s" % (tl(i), tl(o))


def texto_export(e):
    via, fase = e.get("via"), e.get("fase")
    arqs = ", ".join(base(a) for a in (e.get("arquivos") or [])) or ""
    if via == "premiere":
        tr = e.get("trecho") or {}
        trecho = ""
        t_in = tr.get("in") if tr.get("in") is not None and tr.get("in") >= 0 else None
        t_out = tr.get("out") if tr.get("out") is not None and tr.get("out") >= 0 else None
        if t_out is not None:
            ate_fim = tr.get("fim") is not None and abs(t_out - tr["fim"]) <= 0.05
            trecho = " (%s-%s)" % ("começo" if t_in is None else tl(t_in), "fim da sequência" if ate_fim else tl(t_out))
        elif t_in is not None:
            trecho = " (%s-fim)" % tl(t_in)
        if e.get("sucesso") is False:
            return "export do Premiere NÃO terminou bem (estado %s)%s" % (e.get("estado"), trecho)
        if fase == "pronto":
            return "exportou pelo Premiere%s%s" % (" '" + e["sequencia"] + "'" if e.get("sequencia") else "", trecho)
        return "export do Premiere: %s" % fase
    if fase == "fila":
        return "mandou pra fila do Media Encoder%s" % ((" (trabalho %s)" % e["job"]) if e.get("job") else "")
    if fase == "progresso":
        return "Media Encoder renderizando: %d%%" % int(round((e.get("progresso") or 0) * 100))
    if fase == "pronto":
        return "Media Encoder terminou%s" % (": " + arqs if arqs else "")
    if fase == "erro":
        return "Media Encoder deu ERRO%s" % ((" (código %s)" % e["erro_n"]) if e.get("erro_n") is not None else "")
    if fase == "cancelado":
        return "cancelou o render no Media Encoder"
    return "export %s %s" % (via, fase)


# ------------------------------------------------------------------ desfazer (camada 2: avesso exato)
# Revisao 14/10 (REVISAO-resumo 1/2/3/7, REVISAO-desempenho 3):
#  - a timeline e comparada FOTO A FOTO: so e DESFEZ quando a foto nova e o avesso da foto anterior INTEIRA
#    (tudo que mudou naquela foto voltou e nada mais mudou) com pelo menos uma mudanca continua (tempo que andou).
#    O razor desfeito vira UMA linha DESFEZ (antes: "apagou" falso + DESFEZ). Foto que volta so em parte = fraca.
#  - parametro que volta ao PADRAO (duplo clique / Reset: Exposicao 0, Escala 100...) = fraco ("voltou ao padrao").
#  - Z / Shift+Z / Z: tudo aponta pro evento ORIGINAL, que guarda o historico (_hist) e o estado final.
#  - indice por estado (dicionario) + esquecimento dos > 60 s: linear (antes comparava cada mudanca com todas).
DOM_POR_SEQ = ("timeline", "transicao", "efeito", "efeito_kf", "efeito_lista", "faixa_mute", "faixa_renomeou", "faixa_existe", "io")


def _r(x, n=3):
    try:
        return None if x is None else round(float(x), n)
    except (TypeError, ValueError):
        return None


def _est(v):
    """estado comparavel (texto JSON): igualdade exata = avesso"""
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def est_item(x):
    """estado de um clipe da timeline. O painel manda os tempos com 3 casas: igualdade no milissegundo."""
    if not x:
        return _est(None)
    vel = x.get("vel")
    return _est([x.get("faixa") or "", _r(x.get("inicio")), _r(x.get("fim")), _r(x.get("in")), _r(x.get("out")),
                 x.get("nome") or "", (x.get("caminho") or "").lower(), bool(x.get("desligado")), _r(1 if vel is None else vel, 4)])


def valor_padrao(match, nome):
    """valor PADRAO do parametro (o que o duplo clique no slider / o botao Reset devolve). None = nao sei."""
    m, n = (match or "").lower(), (nome or "").lower()
    if "lumetri" in m:
        return 100 if ("satura" in n or "intens" in n) else 0
    if "motion" in m:
        if n.startswith(("escala", "scale", "largura da escala")):
            return 100
        if n.startswith(("rota", "anti")):
            return 0
        return None
    if "opacity" in m:
        return 100 if n.startswith(("opacidade", "opacity")) else None
    if "volume" in m:
        # SONDA 14/10: o volume vem em AMPLITUDE, nao em dB: 0 dB (o padrao) = 0,17782794 (Nivel, Esquerda, Direita)
        return AMP_0DB if n.startswith(("nível", "nivel", "level", "esquerda", "direita", "left", "right")) else None
    return None


def eh_padrao(ef, p, v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    pd = valor_padrao((ef or {}).get("match"), nome_param(p))
    if pd is None:
        pd = valor_padrao((ef or {}).get("match"), (p or {}).get("nome"))
    if pd is not None and eh_volume(ef):
        return v > 0 and abs(db_volume(v)) < 0.05          # 0 dB, com folga do arredondamento do painel
    return pd is not None and abs(v - pd) < 1e-6


def mudancas_atomicas(eventos):
    """Cada mudanca vira {e, t, dom, chave, sa, sd, forte, unid}. Avesso = mesmo dom/chave com sa<->sd trocados.
    forte = valor continuo voltou EXATO (trim, mover, parametro fora do padrao, nome, entrada/saida).
    fraco = liga/desliga ou poe/tira (transicao, efeito, bin, clipe, faixa, mute) ou escolha discreta (mover de bin,
            parametro que voltou ao PADRAO): sai como "volta ao estado de antes (Ctrl+Z ou a mao)".
    unid = (seq_id, carga, foto) da timeline: a foto inteira e comparada junta."""
    out = []

    def add(e, dom, chave, sa, sd, forte, unid=None):
        if forte:
            e["_forte"] = True
        out.append({"e": e, "t": e["t"], "dom": dom, "chave": chave, "sa": sa, "sd": sd, "forte": forte,
                    "unid": unid, "seq": e.get("seq_id")})

    for e in eventos:
        tp = e.get("tipo")
        if tp == "timeline":
            a, d = e.get("antes"), e.get("depois")
            forte = bool(a and d and (any(abs((a.get(c) or 0) - (d.get(c) or 0)) > EXATO for c in ("inicio", "fim", "in", "out"))
                                      or a.get("faixa") != d.get("faixa") or (a.get("vel") or 1) != (d.get("vel") or 1)))
            add(e, "timeline", None, est_item(a), est_item(d), forte,
                (e.get("seq_id"), e.get("carga"), e.get("foto")) if e.get("foto") is not None else None)
        elif tp == "faixa" and e.get("mudanca") in ("nova", "apagada"):
            # faixa criada e apagada (a mao ou Ctrl+Z) = por/tirar: fraco (REVISAO-resumo 7)
            f = e.get("faixa")
            pres, aus = _est(["faixa", f, "presente"]), _est(["faixa", f, "ausente"])
            sa, sd = (aus, pres) if e["mudanca"] == "nova" else (pres, aus)
            add(e, "faixa_existe", (f,), sa, sd, False,
                (e.get("seq_id"), e.get("carga"), e.get("foto")) if e.get("foto") is not None else None)
        elif tp == "marcador":
            m = e.get("depois") or e.get("antes") or {}
            dono = (e.get("mestre") or {}).get("id") if e.get("alvo") == "clipe" else "seq"
            add(e, "marcador", (dono, m.get("id")), _est(e.get("antes")), _est(e.get("depois")), e.get("mudanca") == "mudou")
        elif tp == "efeito" and e.get("mudanca") in ("param", "colocou", "tirou", "keyframe"):
            it = e.get("item") or {}
            ef = e.get("efeito") or {}
            if e["mudanca"] == "param":
                p = e.get("param") or {}
                add(e, "efeito", (it.get("faixa"), it.get("inicio"), ef.get("match"), p.get("idx")),
                    _est(p.get("antes")), _est(p.get("depois")), not eh_padrao(ef, p, p.get("depois")))
            elif e["mudanca"] == "keyframe":
                p = e.get("param") or {}
                add(e, "efeito_kf", (it.get("faixa"), it.get("inicio"), ef.get("match"), p.get("idx")),
                    _est(p.get("antes_n")), _est(p.get("depois_n")), False)
            else:
                presente = e["mudanca"] == "colocou"
                add(e, "efeito_lista", (it.get("faixa"), it.get("inicio"), ef.get("match")), _est(not presente), _est(presente), False)
        elif tp == "transicao" and e.get("mudanca") != "contagem":
            x = e.get("depois") or e.get("antes") or {}

            def tr_est(t):
                return None if not t else [t.get("faixa"), t.get("inicio"), t.get("fim"), t.get("nome")]
            add(e, "transicao", (x.get("faixa"),), _est(tr_est(e.get("antes"))), _est(tr_est(e.get("depois"))),
                e.get("mudanca") in ("duracao", "trocou"))
        elif tp == "faixa" and e.get("mudanca") in ("mute", "renomeou"):
            add(e, "faixa_" + e["mudanca"], (e.get("faixa"),), _est(e.get("antes")), _est(e.get("depois")), e["mudanca"] == "renomeou")
        elif tp == "projeto" and e.get("mudanca") in ("renomeou", "moveu", "criou_bin", "criou_sequencia", "importou", "apagou", "novo"):
            it = e.get("item") or {}
            m = e["mudanca"]
            if m == "renomeou":
                add(e, "proj_nome", (it.get("id"),), _est((e.get("antes") or {}).get("nome")), _est(it.get("nome")), True)
            elif m == "moveu":
                # arrastar de volta pro bin de antes e tao facil quanto o Ctrl+Z: escolha discreta = fraco
                add(e, "proj_bin", (it.get("id"),), _est((e.get("antes") or {}).get("bin")), _est(it.get("bin")), False)
            else:
                # existe + conteudo: "criou bin vazio" so e o avesso de "apagou bin VAZIO"
                estado = _est({"existe": True, "conteudo": e.get("conteudo") or 0})
                if m == "apagou":
                    add(e, "proj_existe", (it.get("id"),), estado, _est(None), False)
                else:
                    add(e, "proj_existe", (it.get("id"),), _est(None), estado, False)
        elif tp == "entrada_saida":
            add(e, "io", ("io",), _est(e.get("antes")), _est(e.get("depois")), True)
    return out


def _hist(e, t, tipo):
    h = e.setdefault("_hist", [])
    if (t, tipo) not in h:
        h.append((t, tipo))


def achar_avessos(atomicas):
    """Marca nos eventos:
      forte: _desfaz (evento ORIGINAL) no avesso; avesso de um desfazer = _refaz (o original); avesso de um refazer =
             _desfaz (o original de novo). O original guarda _hist = [(t, "desfeita"|"refeita"), ...].
             _snap = a foto que voltou so tem bordas em ponto de snap (voltar a mao e plausivel).
      fraco: _volta (evento que ele desfez) no avesso e _revertido_em (t) no original; _padrao = voltou ao valor padrao.
    Sempre "provavel": nao existe aviso de Ctrl+Z na API."""
    ops, por_unid = [], {}
    for c in atomicas:
        u = c["unid"]
        if u is not None:
            if u not in por_unid:
                por_unid[u] = {"t": c["t"], "cs": [], "seq": c["seq"], "vivo": True}
                ops.append(por_unid[u])
            por_unid[u]["cs"].append(c)
        else:
            ops.append({"t": c["t"], "cs": [c], "seq": c["seq"], "solta": True, "vivo": True})
    ops.sort(key=lambda o: o["t"])      # estavel: mesma hora mantem a ordem do arquivo

    idx = {}            # (dom, chave, sa, sd) -> [mudancas abertas]
    fila = deque()      # (t, chave do indice, mudanca): esquece o que passou de 60 s
    unids = {}          # assinatura do AVESSO da foto -> [fotos abertas]

    def tirar_do_indice(c):
        k = (c["dom"], c["chave"], c["sa"], c["sd"])
        lst = idx.get(k)
        if lst:
            for i in range(len(lst)):
                if lst[i] is c:
                    del lst[i]
                    break
            if not lst:
                del idx[k]

    def usar(c):
        tirar_do_indice(c)
        if c.get("op") is not None:
            c["op"]["vivo"] = False      # foto que perdeu um pedaco nao pode mais ser desfeita "inteira"

    def abrir(op):
        for c in op["cs"]:
            c["op"] = op
            k = (c["dom"], c["chave"], c["sa"], c["sd"])
            idx.setdefault(k, []).append(c)
            fila.append((c["t"], k, c))
        if not op.get("solta"):
            inv = (op["seq"], tuple(sorted(c["sd"] + "\x00" + c["sa"] for c in op["cs"])))
            unids.setdefault(inv, []).append(op)

    def marcar(c1, c2, forte, t2):
        e1, e2 = c1["e"], c2["e"]
        if not forte:
            e2["_volta"] = e1
            e1["_revertido_em"] = t2
            return
        if e1.get("_desfaz") is not None:           # avesso de um desfazer = refez a mudanca original
            orig = e1["_desfaz"]
            e2["_refaz"] = orig
            _hist(orig, t2, "refeita")
        elif e1.get("_refaz") is not None:          # avesso de um refazer = desfez de novo a original
            orig = e1["_refaz"]
            e2["_desfaz"] = orig
            _hist(orig, t2, "desfeita")
        else:
            e2["_desfaz"] = e1
            _hist(e1, t2, "desfeita")

    for op in ops:
        t2 = op["t"]
        while fila and t2 - fila[0][0] > JANELA_DESFAZER:
            _, _k, c = fila.popleft()
            tirar_do_indice(c)
        cs = op["cs"]
        if not op.get("solta"):
            assin = (op["seq"], tuple(sorted(c["sa"] + "\x00" + c["sd"] for c in cs)))
            cand = None
            for o1 in reversed(unids.get(assin, [])):
                if o1["vivo"] and o1 is not op and t2 - o1["t"] <= JANELA_DESFAZER:
                    cand = o1
                    break
            if cand is not None:
                # a foto nova e o avesso da foto anterior INTEIRA
                livres = {}
                for c1 in cand["cs"]:
                    livres.setdefault((c1["sa"], c1["sd"]), []).append(c1)
                forte = any(c["forte"] for c in cs)
                tl_cs = [c for c in cs if c["dom"] == "timeline"]
                snap = bool(tl_cs) and all(c["e"].get("antes") and c["e"].get("depois") and c["e"].get("snap") for c in tl_cs)
                for c2 in cs:
                    c1 = livres[(c2["sd"], c2["sa"])].pop()
                    usar(c1)
                    marcar(c1, c2, forte, t2)
                    if forte and snap:
                        c2["e"]["_snap"] = True
                cand["vivo"] = False
                abrir(op)
                continue
        # mudanca a mudanca: foto que volta SO EM PARTE = fraca; mudanca solta = a regra forte/fraca dela
        parcial = not op.get("solta")
        for c2 in cs:
            achou = None
            for c1 in reversed(idx.get((c2["dom"], c2["chave"], c2["sd"], c2["sa"]), [])):
                if c1.get("op") is op or t2 - c1["t"] > JANELA_DESFAZER:
                    continue
                if c1["seq"] != c2["seq"] and c2["dom"] in DOM_POR_SEQ:
                    continue
                achou = c1
                break
            if achou is None:
                continue
            usar(achou)
            if parcial:
                forte = False
            elif c2["dom"] == "efeito":
                forte = c2["forte"]          # so importa pra onde o valor VOLTOU (padrao = fraco)
            else:
                forte = achou["forte"] and c2["forte"]
            if c2["dom"] == "efeito" and not c2["forte"]:
                c2["e"]["_padrao"] = True
            marcar(achou, c2, forte, t2)
        abrir(op)


def sufixo_volta(e):
    o = e.get("_volta")
    if o is None:
        return ""
    if e.get("_padrao"):
        return " (voltou ao padrão: duplo clique/Reset ou Ctrl+Z)"
    return " (volta ao estado de antes de %s: Ctrl+Z ou à mão)" % rec(o["t"])


def marca_decisao(refs):
    """sufixo da decisao: historico de desfeita/refeita (com o estado final quando vai e volta) ou 'voltou atras'"""
    hist = sorted(set(h for r in refs for h in (r.get("_hist") or [])))
    if hist:
        partes, vistos = [], {"desfeita": 0, "refeita": 0}
        for t, k in hist:
            vistos[k] += 1
            partes.append("%s%s em %s" % (k, " de novo" if vistos[k] > 1 else "", rec(t)))
        s = " (" + ", ".join(partes)
        if len(hist) >= 3:
            s += " -> ficou %s" % ("DESFEITA" if hist[-1][1] == "desfeita" else "feita")
        return s + ")"
    rev = [r.get("_revertido_em") for r in refs if r.get("_revertido_em") is not None]
    if rev:
        return " (voltou atrás em %s)" % rec(min(rev))
    return ""


def texto_som_pc(meta, partes, saidas):
    """Linha '- som do PC: ...' do cabecalho + o resumo do sinal pro 'arquivos:' (14/10, trilha separada do PC).
    Sessao de antes de 14/10 (sem o campo) = nenhuma linha."""
    if meta.get("gravar_som_pc") is None:
        return "", ""
    if not meta.get("gravar_som_pc"):
        return "- som do PC: não gravado (desligado no config: \"gravar_som_pc\": false)", ""
    pico_db, com_som = saidas.get("pc_pico_db"), saidas.get("pc_seg_com_som") or 0
    if not saidas.get("pc"):
        sinal = ""
    elif pico_db is None:
        sinal = "silêncio: nada tocou no PC"
    elif not com_som:
        sinal = "quase silêncio: pico %s dB, nada acima de -50 dB" % num(pico_db)
    else:
        sinal = "teve som: pico %s dB, ~%s com som" % (num(pico_db), dur(com_som))
    disps, falhas, motivos, trocas, reaberturas = [], [], [], 0, 0
    for p in partes:
        if not p.get("pc"):
            continue
        for d in p.get("pc_dispositivos") or []:
            if d not in disps:
                disps.append(d)
        trocas += sum(1 for e in p.get("pc_eventos") or [] if e.get("o_que") == "trocou")
        reaberturas += p.get("pc_reaberturas") or 0
        if p.get("pc_caiu_em") and p.get("inicio"):
            falhas.append("%d (parou em %s)" % (p["n"], rec((p.get("t0") or 0) + p["pc_caiu_em"] - p["inicio"])))
        elif not p.get("pc_ok"):
            falhas.append(str(p["n"]))
            if p.get("erro_pc") and p["erro_pc"] not in motivos:
                motivos.append(p["erro_pc"])
    teste = " [TESTE: saída falsa, nada tocou]" if meta.get("som_pc_falso") else ""
    if not saidas.get("pc"):
        return ("- som do PC: NÃO gravou%s (a sessão seguiu só com o microfone)%s"
                % ((" - " + "; ".join(motivos)) if motivos else "", teste)), ""
    estado = "ok" if not falhas else "FALHOU na(s) parte(s) %s%s (silêncio no pc.wav nesse trecho)" % (
        ", ".join(falhas), (" - " + "; ".join(motivos)) if motivos else "")
    extra = (" · a saída de som trocou %d vez(es) no meio (ver SOM DO PC na linha do tempo)" % trocas) if trocas else ""
    if reaberturas:
        # revisao 14/10: o loopback parou sozinho e voltou no mesmo aparelho (ate ~2 s de silencio em cada)
        extra += " · o gravador do som do PC reabriu sozinho %d vez(es) (até ~2 s de silêncio em cada)" % reaberturas
    return ("- som do PC: %s - %s · %s%s%s" % (" -> ".join(disps) or "?", estado, sinal, extra, teste)), sinal


# ------------------------------------------------------------------ montagem
def gerar(pasta, meta=None):
    pasta = Path(pasta)
    meta_arq, eventos = ler(pasta)
    meta = meta or meta_arq
    seq_nomes = {}
    linhas = []             # (t, ordem, texto)
    decisoes = []           # [t, frase_txt, cat, refs(eventos)]
    selecoes = []           # (t, evento)
    contexto_evs = {"fonte": [], "clique": [], "navalha": []}
    conferir = []           # (t, texto) - so a tela mostra
    contagem = {"corte": 0, "trim": 0, "apagou": 0, "novo": 0, "moveu": 0, "slip": 0, "ligado": 0, "outro": 0,
                "ripple": 0, "marcador": 0, "selecao": 0, "velocidade": 0,
                "marcador_seq": 0, "marcador_clipe": 0, "ef_colocou": 0, "ef_tirou": 0, "ajustes": 0, "keyframes": 0,
                "tr_colocou": 0, "tr_tirou": 0, "tr_duracao": 0, "tr_trocou": 0, "tr_contagem": 0,
                "fx_mute": 0, "fx_nova": 0, "fx_apagada": 0, "fx_trava": 0, "fx_renomeou": 0,
                "textos": 0, "leg_nova": 0, "leg_apagada": 0, "leg_mudou": 0,
                "pj_importou": 0, "pj_bin": 0, "pj_seq": 0, "pj_renomeou": 0, "pj_moveu": 0, "pj_apagou": 0, "pj_outro": 0,
                "exp_premiere": 0, "exp_ame": 0, "desfez": 0, "refez": 0, "voltas": 0, "fonte": 0, "io": 0}
    ajuste_clipes = set()
    ajuste_cat = {}
    zeros = {}
    capac = {}
    desemp = None
    painel_ver = None

    # desfazer: camada 2 (avesso exato) antes de escrever qualquer linha
    achar_avessos(mudancas_atomicas(eventos))

    # desfazer: camada 1 do painel (a timeline INTEIRA voltou a um estado ja fotografado). Vale quando a camada 2
    # nao explicou a foto: Ctrl+Z de VARIOS passos de uma vez, ou fora da janela de 60 s. Se a camada 2 achou so
    # avesso fraco de UM passo (por/tirar, faixa criada e apagada), a camada 2 vence (REVISAO-resumo 7).
    por_foto = {}
    for e in eventos:
        if e.get("foto") is not None and e.get("tipo") in ("timeline", "faixa", "transicao", "texto", "entrada_saida"):
            por_foto.setdefault((e.get("seq_id"), e.get("carga"), e.get("foto")), []).append(e)
    desfeita_c1 = {}        # foto -> evento desfazer_provavel (a foto vira UMA linha DESFEZ)
    for e in eventos:
        if e.get("tipo") != "desfazer_provavel" or e.get("alvo") != "timeline":
            continue
        F = (e.get("seq_id"), e.get("carga"), e.get("foto"))
        mesma = por_foto.get(F, [])
        if any(x.get("_desfaz") is not None or x.get("_refaz") is not None for x in mesma):
            continue
        passos = e.get("desfaz_fotos") or []
        if len(passos) <= 1 and any(x.get("_volta") is not None for x in mesma):
            continue
        if mesma and not any(x.get("_forte") for x in mesma):
            continue            # so por/tirar: "Ctrl+Z ou à mão" (as linhas normais ficam)
        desfeita_c1[F] = e
        for n in passos:
            for x in por_foto.get((e.get("seq_id"), e.get("carga"), n), []):
                _hist(x, e["t"], "desfeita")
    ms_ordenados = sorted((x.get("ms"), x["t"]) for x in eventos if x.get("ms"))
    ms_chaves = [m for m, _ in ms_ordenados]

    def t_do_ms(ms):
        i = bisect.bisect_left(ms_chaves, ms)
        melhor = None
        for j in (i - 1, i):
            if 0 <= j < len(ms_ordenados) and abs(ms_ordenados[j][0] - ms) < 2000:
                if melhor is None or abs(ms_ordenados[j][0] - ms) < abs(melhor[0] - ms):
                    melhor = ms_ordenados[j]
        return melhor[1] if melhor else None

    def na_foto_desfeita(e):
        return e.get("foto") is not None and (e.get("seq_id"), e.get("carga"), e.get("foto")) in desfeita_c1

    # agulha
    agulhas = [e for e in eventos if e.get("tipo") == "agulha"]
    movs = movimentos(agulhas)
    for t, txt, m in descrever_movimentos(movs):
        linhas.append((t, O_AGULHA, "AGULHA - " + txt))

    def decide(t, txt, cat, refs):
        decisoes.append([t, txt, cat, [r for r in refs if r is not None]])

    def linha_desfez(e, txt_original, t_orig):
        contagem["desfez"] += 1
        linhas.append((e["t"], O_DESFAZ, "DESFEZ (provável Ctrl+Z) - desfez o que fez em %s: %s" % (rec(t_orig), txt_original)))

    def volta(e):
        if e.get("_volta") is not None:
            contagem["voltas"] += 1
        return sufixo_volta(e)

    def linha_refez(e, txt_original, t_orig):
        contagem["refez"] += 1
        linhas.append((e["t"], O_DESFAZ, "REFEZ (provável Ctrl+Shift+Z) - refez o que tinha desfeito: %s (feito primeiro em %s)" % (txt_original, rec(t_orig))))

    # textos de cada evento (pra citar no DESFEZ)
    textos_ev = {}

    # timeline agrupada por leitura (+ eventos da mesma foto)
    grupos = {}
    texto_por_foto = set()
    efeitos_grupos = {}
    projetos_grupos = {}
    for e in eventos:
        tipo = e.get("tipo")
        if tipo == "sequencia":
            seq_nomes[e.get("seq_id")] = e.get("nome")
            if e.get("zero"):
                zeros[e.get("nome")] = e.get("zero")
            primeiro = not any(x[2].startswith("SEQUÊNCIA") for x in linhas)
            verbo = "começou na sequência" if primeiro else "abriu a sequência"
            linhas.append((e["t"], O_SEQ, "SEQUÊNCIA - %s '%s'%s" % (verbo, e.get("nome"), (" (projeto %s)" % e.get("projeto")) if e.get("projeto") else "")))
        elif tipo == "selecao":
            contagem["selecao"] += 1
            selecoes.append((e["t"], e))
            linhas.append((e["t"], O_CONTEXTO, "SELEÇÃO - " + texto_selecao(e)))
        elif tipo == "foto_inicial":
            por = {}
            for it in e.get("itens") or []:
                por[it.get("faixa")] = por.get(it.get("faixa"), 0) + 1
            det = ", ".join("%s: %d" % (f, por[f]) for f in sorted(por, key=ordem_faixa))
            nome = seq_nomes.get(e.get("seq_id"), "?")
            ms = e.get("ms_leitura")
            extra = []
            fx = e.get("faixas") or {}
            mudas = [("V%d" % (i + 1)) for i, x in enumerate(fx.get("V") or []) if x.get("mudo")] + \
                    [("A%d" % (i + 1)) for i, x in enumerate(fx.get("A") or []) if x.get("mudo")]
            if mudas:
                extra.append("mudas/escondidas: " + ", ".join(mudas))
            if e.get("transicoes"):
                extra.append("%d transição(ões)" % e["transicoes"])
            if fx.get("L"):
                extra.append("%d faixa(s) de legenda" % fx["L"])
            linhas.append((e["t"], O_SEQ, "TIMELINE - foto inicial de '%s': %d itens (%s)%s%s" % (
                nome, len(e.get("itens") or []), det or "vazia", (" - leitura levou %s" % dur(ms / 1000.0)) if ms else "",
                (" · " + "; ".join(extra)) if extra else "")))
        elif tipo == "timeline":
            grupos.setdefault((e.get("seq_id"), e.get("carga"), e.get("foto")), []).append(e)
        elif tipo == "marcador":
            txt = texto_marcador(e)
            textos_ev[id(e)] = txt
            if e.get("_desfaz") is not None:
                linha_desfez(e, "MARCADOR - " + textos_ev.get(id(e["_desfaz"]), "o marcador"), e["_desfaz"]["t"])
                continue
            if e.get("_refaz") is not None:
                linha_refez(e, textos_ev.get(id(e["_refaz"]), txt), e["_refaz"]["t"])
                continue
            contagem["marcador"] += 1
            contagem["marcador_clipe" if e.get("alvo") == "clipe" else "marcador_seq"] += 1
            txt += volta(e)
            linhas.append((e["t"], O_MUDANCA, "MARCADOR - " + txt))
            decide(e["t"], txt, "marcador", [e])
        elif tipo == "painel" and e.get("msg"):
            if "começou a registrar" in e["msg"]:
                painel_ver = e["msg"].split(" começou")[0]
            linhas.append((e["t"], O_PAINEL, "(painel: %s)" % e.get("msg")))
        elif tipo == "capacidades":
            for k in ("ouvintes", "existe", "leituras", "campos", "disparos"):
                if isinstance(e.get(k), dict):
                    capac.setdefault(k, {}).update(e[k])
            if e.get("versao"):
                capac["versao"] = e["versao"]
        elif tipo == "desempenho":
            desemp = e
        elif tipo == "efeito":
            # (carga, leitura): o numero da leitura volta a 1 se o painel recarregar (REVISAO-resumo 8)
            efeitos_grupos.setdefault((e.get("carga"), e.get("leitura"), (e.get("item") or {}).get("faixa"), (e.get("item") or {}).get("inicio"),
                                       (e.get("efeito") or {}).get("match"), e.get("mudanca") if e.get("mudanca") != "param" else "param"), []).append(e)
        elif tipo == "transicao":
            txt = texto_transicao(e)
            textos_ev[id(e)] = txt
            if na_foto_desfeita(e):
                continue
            if e.get("_desfaz") is not None:
                linha_desfez(e, "TRANSIÇÃO - " + textos_ev.get(id(e["_desfaz"]), "a transição"), e["_desfaz"]["t"])
                continue
            if e.get("_refaz") is not None:
                linha_refez(e, textos_ev.get(id(e["_refaz"]), txt), e["_refaz"]["t"])
                continue
            m = e.get("mudanca")
            contagem["tr_" + m] = contagem.get("tr_" + m, 0) + 1
            txt += volta(e)
            linhas.append((e["t"], O_MUDANCA, "TRANSIÇÃO - " + txt))
            decide(e["t"], "TRANSIÇÃO - " + txt, "transição", [e])
            if m == "contagem":
                conferir.append((e["t"], "transição em %s: o Premiere só deixou contar (ver qual na tela)" % e.get("faixa")))
        elif tipo == "faixa":
            txt = texto_faixa(e)
            textos_ev[id(e)] = txt
            if na_foto_desfeita(e):
                continue
            m = e.get("mudanca")
            if e.get("_desfaz") is not None:
                linha_desfez(e, "FAIXA - " + textos_ev.get(id(e["_desfaz"]), "a faixa " + str(e.get("faixa"))), e["_desfaz"]["t"])
                continue
            if e.get("_refaz") is not None:
                linha_refez(e, textos_ev.get(id(e["_refaz"]), txt), e["_refaz"]["t"])
                continue
            chave = {"mute": "fx_mute", "nova": "fx_nova", "apagada": "fx_apagada", "trava_alternou": "fx_trava", "renomeou": "fx_renomeou"}.get(m)
            if chave:
                contagem[chave] += 1
            txt += volta(e)
            linhas.append((e["t"], O_MUDANCA, "FAIXA - " + txt))
            if m == "trava_alternou":
                conferir.append((e["t"], "cadeado de %s: travou ou destravou?" % e.get("faixa")))
            else:
                decide(e["t"], "FAIXA - " + txt, "faixa", [e])
        elif tipo == "texto":
            txt = texto_texto(e)
            if na_foto_desfeita(e):
                continue
            contagem["textos"] += 1
            if e.get("foto") is not None:
                it = e.get("item") or {}
                texto_por_foto.add((e.get("seq_id"), e.get("carga"), e.get("foto"), it.get("faixa"), round(it.get("inicio") or 0, 2)))
            linhas.append((e["t"], O_MUDANCA, "TEXTO - " + txt))
            decide(e["t"], "TEXTO - " + txt, "texto", [e])
            if e.get("fonte") in ("nome_do_clipe", "nenhuma", None) or not e.get("depois"):
                conferir.append((e["t"], "texto em [%s] %s: conferir o que ficou escrito" % ((e.get("item") or {}).get("faixa"), tl((e.get("item") or {}).get("inicio")))))
        elif tipo == "legenda":
            txt = texto_legenda(e)
            contagem["leg_" + (e.get("mudanca") or "mudou")] = contagem.get("leg_" + (e.get("mudanca") or "mudou"), 0) + 1
            linhas.append((e["t"], O_MUDANCA, "LEGENDA - " + txt))
            decide(e["t"], "LEGENDA - " + txt, "legenda", [e])
            conferir.append((e["t"], "legenda %s-%s: o texto só aparece na tela" % (tl(e.get("inicio")), tl(e.get("fim")))))
        elif tipo == "projeto":
            projetos_grupos.setdefault((e.get("carga"), e.get("leitura")), []).append(e)
        elif tipo == "projeto_inicial":
            linhas.append((e["t"], O_SEQ, "PROJETO - leitura inicial%s: %d itens (%d bins, %d sequências, %d mídias)%s" % (
                (" de '%s'" % e["projeto"]) if e.get("projeto") else "",
                e.get("total") or 0, e.get("bins") or 0, e.get("sequencias") or 0, e.get("midias") or 0,
                (" - leitura levou %s" % dur((e.get("ms_leitura") or 0) / 1000.0)) if e.get("ms_leitura") else "")))
        elif tipo == "projeto_selecao":
            nomes = [x.get("nome") or "?" for x in (e.get("itens") or [])]
            if not nomes:
                continue
            contexto_evs["clique"].append((e["t"], nomes))
            txt = "selecionou %s no painel Projeto" % (", ".join(nomes[:5]) + (" e mais %d" % (len(nomes) - 5) if len(nomes) > 5 else ""))
            ult = linhas[-1] if linhas else None
            if ult and ult[2].startswith("PROJETO (clique)") and e["t"] - ult[0] <= 3.0:
                linhas[-1] = (ult[0], ult[1], ult[2] + "; depois " + ", ".join(nomes[:5]))
            else:
                linhas.append((e["t"], O_CONTEXTO, "PROJETO (clique) - " + txt))
        elif tipo == "export":
            txt = texto_export(e)
            fase = e.get("fase")
            if fase == "progresso":
                continue
            if fase == "pronto":
                contagem["exp_premiere" if e.get("via") == "premiere" else "exp_ame"] += 1
            if fase == "pronto" and e.get("via") == "premiere" or fase == "fila":
                decide(e["t"], "EXPORT - " + txt, "marco", [e])
            if fase in ("erro", "cancelado"):
                conferir.append((e["t"], "export: %s (o motivo só na tela)" % txt))
            linhas.append((e["t"], O_EXPORT, "EXPORT - " + txt))
        elif tipo == "fonte":
            contagem["fonte"] += 1
            nome = e.get("nome") or base(e.get("caminho")) or "?"
            contexto_evs["fonte"].append((e["t"], nome))
            linhas.append((e["t"], O_CONTEXTO, "FONTE - abriu %s no monitor de origem%s" % (nome, (" (em %s)" % tl(e.get("pos"))) if e.get("pos") else "")))
        elif tipo == "entrada_saida":
            d, a = e.get("depois") or {}, e.get("antes") or {}
            if d.get("in") is None and d.get("out") is None:
                txt = "tirou a marcação (antes %s)" % io_txt(a)
            else:
                txt = "marcou %s (antes %s)" % (io_txt(d), io_txt(a))
            if na_foto_desfeita(e):
                continue
            if e.get("_desfaz") is not None:
                linha_desfez(e, "ENTRADA/SAÍDA - " + textos_ev.get(id(e["_desfaz"]), "a entrada/saída"), e["_desfaz"]["t"])
                continue
            if e.get("_refaz") is not None:
                linha_refez(e, "ENTRADA/SAÍDA - " + textos_ev.get(id(e["_refaz"]), txt), e["_refaz"]["t"])
                continue
            contagem["io"] += 1
            textos_ev[id(e)] = txt
            linhas.append((e["t"], O_CONTEXTO, "ENTRADA/SAÍDA - " + txt + volta(e)))
        elif tipo == "ferramenta":
            if e.get("qual") == "navalha":
                contexto_evs["navalha"].append(e["t"])
                ult = [x for x in linhas if x[2].startswith("FERRAMENTA - com a navalha")]
                if ult and e["t"] - ult[-1][0] <= 30:
                    continue
                linhas.append((e["t"], O_CONTEXTO, "FERRAMENTA - com a navalha (C) na mão, grudando na agulha/marcador"))
            elif e.get("qual") == "limite_da_midia":
                linhas.append((e["t"], O_CONTEXTO, "FERRAMENTA - o trim bateu no limite da mídia (acabou o material)"))
        elif tipo == "desfazer":
            contagem["desfez" if e.get("qual") != "refez" else "refez"] += 1
            linhas.append((e["t"], O_DESFAZ, "%s (Ctrl+%sZ, aviso do Premiere)" % ("REFEZ" if e.get("qual") == "refez" else "DESFEZ", "Shift+" if e.get("qual") == "refez" else "")))

    # ---- timeline: grupos por leitura
    fotos_t = {}
    for (sid, carga, foto), grupo in grupos.items():
        fotos_t[(sid, carga, foto)] = min(e["t"] for e in grupo)
    textos_cat = {}
    ag_ms = [(e.get("ms"), e) for e in agulhas if e.get("ms") is not None]
    ag_ms.sort(key=lambda x: x[0])
    ag_chaves = [m for m, _ in ag_ms]

    def t_do_corte(grupo, pos):
        """corte feito com a agulha TOCANDO (Ctrl+K no beat, REVISAO-resumo 4): o segundo em que a agulha passou
        pela posicao do corte (dentro da janela da foto). None = agulha parada: fica o segundo da foto/aviso."""
        jan = next((e.get("janela_ms") for e in grupo if e.get("janela_ms")), None)
        if not jan or pos is None:
            return None
        i = max(0, bisect.bisect_left(ag_chaves, jan[0] - 1000) - 1)
        while i + 1 < len(ag_ms) and ag_ms[i][0] <= jan[1] + 500:
            a1, a2 = ag_ms[i][1], ag_ms[i + 1][1]
            if (a2.get("tocando") and a1.get("seq_id") == a2.get("seq_id") == grupo[0].get("seq_id")
                    and a1.get("pos") is not None and a2.get("pos") is not None and a2["pos"] > a1["pos"]
                    and a1["pos"] - EPS <= pos <= a2["pos"] + EPS):
                return a1["t"] + (pos - a1["pos"]) / (a2["pos"] - a1["pos"]) * (a2["t"] - a1["t"])
            i += 1
        return None

    def linha_desfeita_c1(F, t):
        e = desfeita_c1[F]
        volta_t = fotos_t.get((e.get("seq_id"), e.get("carga"), e.get("volta_a_foto")))
        if volta_t is None and e.get("volta_a_ms"):
            volta_t = t_do_ms(e["volta_a_ms"])
        passos = e.get("desfaz_fotos") or []
        txts = []
        for n in passos:
            for x in por_foto.get((e.get("seq_id"), e.get("carga"), n), []):
                tx = textos_ev.get(id(x))
                if tx and tx not in txts:
                    txts.append(tx)
        contagem["desfez"] += 1
        resumo_txt = "; ".join(txts[:4]) + (" e mais %d" % (len(txts) - 4) if len(txts) > 4 else "")
        linhas.append((t, O_DESFAZ, "DESFEZ (provável Ctrl+Z%s) - a timeline voltou exatamente como estava%s%s" % (
            (", %d passos de uma vez" % len(passos)) if len(passos) > 1 else "",
            (" em %s" % rec(volta_t)) if volta_t is not None else "",
            (" (desfez: %s)" % resumo_txt) if resumo_txt else "")))

    for (sid, carga, foto), grupo in grupos.items():
        t = fotos_t[(sid, carga, foto)]
        if (sid, carga, foto) in desfeita_c1:
            linha_desfeita_c1((sid, carga, foto), t)
            continue
        pausa = any(e.get("apos_pausa") for e in grupo)
        desfeitos = [e for e in grupo if e.get("_desfaz") is not None]
        refeitos = [e for e in grupo if e.get("_refaz") is not None]
        normais = [e for e in grupo if e.get("_desfaz") is None and e.get("_refaz") is None]
        for f in interpretar(normais):
            if f.so_nome and any((sid, carga, foto, fx, round(f.pos or 0, 2)) in texto_por_foto for fx in f.faixas):
                continue        # o TEXTO ja conta essa troca de nome
            txt = f.fmt(faixas_txt([x for x in f.faixas if x]))
            if pausa:
                txt = "(mudou durante a pausa) " + txt
            for r in f.refs:
                textos_ev[id(r)] = txt
                textos_cat[id(r)] = f.cat
            voltas = [r for r in f.refs if r.get("_volta") is not None]
            if voltas:
                txt += volta(voltas[0])
            contagem[f.cat] = contagem.get(f.cat, 0) + 1
            rot = "VELOCIDADE - " if f.cat == "velocidade" else "TIMELINE - "
            corpo = txt.replace("VELOCIDADE: ", "") if f.cat == "velocidade" else txt
            tf = t
            if f.cat == "corte":
                tc = t_do_corte(grupo, f.pos)
                if tc is not None:
                    tf = tc
                    for r in f.refs:
                        r["_t_linha"] = tf      # o DESFEZ deste corte cita o mesmo segundo
            linhas.append((tf, O_MUDANCA, rot + corpo))
            if f.decisao:
                decide(tf, (rot + corpo) if f.cat == "velocidade" else corpo, f.cat, f.refs)
        for lista, eh_refaz in ((desfeitos, False), (refeitos, True)):
            if not lista:
                continue
            originais = []
            for e in lista:
                o = e.get("_refaz") if eh_refaz else e.get("_desfaz")
                if o is not None and o not in originais:
                    originais.append(o)
            # a causa antes da consequencia: o ripple ("itens andaram") vai por ultimo
            originais.sort(key=lambda o: 1 if textos_cat.get(id(o)) == "ripple" else 0)
            txts = []
            for o in originais:
                tx = textos_ev.get(id(o))
                if tx and tx not in txts:
                    txts.append(tx)
            t_orig = min(o.get("_t_linha", o["t"]) for o in originais) if originais else t
            nomes = sorted(set((x.get("depois") or x.get("antes") or {}).get("nome") or "?" for x in lista))
            alvo = nomes[0] if len(nomes) == 1 else ("a timeline (%s)" % ", ".join(nomes[:4]) if len(nomes) <= 4 else "a timeline (%d clipes)" % len(nomes))
            resumo_txt = "; ".join(txts[:3]) + (" e mais %d" % (len(txts) - 3) if len(txts) > 3 else "")
            if eh_refaz:
                contagem["refez"] += 1
                linhas.append((t, O_DESFAZ, "REFEZ (provável Ctrl+Shift+Z) - refez o que tinha desfeito: %s (feito primeiro em %s)" % (resumo_txt or "a mudança", rec(t_orig))))
            else:
                contagem["desfez"] += 1
                # tudo que voltou caiu em ponto de snap (borda de clipe parado, agulha, marcador): a mao tambem bate exato
                rot_d = "DESFEZ (Ctrl+Z ou voltou à mão no snap)" if all(e.get("_snap") for e in lista) else "DESFEZ (provável Ctrl+Z)"
                linhas.append((t, O_DESFAZ, "%s - %s voltou como estava antes de %s%s" % (
                    rot_d, alvo, rec(t_orig), (" (desfez: %s)" % resumo_txt) if resumo_txt else "")))
    for F, e in desfeita_c1.items():
        if F not in grupos:
            linha_desfeita_c1(F, e["t"])

    # ---- desfazer de EFEITO do painel (camada 1): so se a camada 2 nao explicou e nao foi volta ao padrao
    t_ef_explicado = sorted(x["t"] for x in eventos if x.get("tipo") == "efeito" and (x.get("_desfaz") is not None or x.get("_volta") is not None))
    for e in eventos:
        if e.get("tipo") != "desfazer_provavel" or e.get("alvo") != "efeito":
            continue
        p = e.get("param") or {}
        i = bisect.bisect_left(t_ef_explicado, e["t"] - 2.0)
        if i < len(t_ef_explicado) and t_ef_explicado[i] <= e["t"] + 2.0:
            continue
        if eh_padrao(e.get("efeito"), p, p.get("voltou_a")):
            continue            # duplo clique / Reset: a linha AJUSTE ja diz "voltou ao padrao"
        contagem["desfez"] += 1
        linhas.append((e["t"], O_DESFAZ, "DESFEZ (provável Ctrl+Z) - %s %s: %s voltou de %s pra %s" % (
            item_curto(e.get("item")), nome_efeito(e.get("efeito")), nome_param(p),
            valor_param_txt(e.get("efeito"), p.get("de")), valor_param_txt(e.get("efeito"), p.get("voltou_a")))))

    # ---- efeitos agrupados (um AJUSTE por clipe + efeito + leitura)
    def fatiar(grupos_d):
        """grupo de leitura -> pedacos sem buraco de mais de 2 s (sessao antiga sem `carga`, painel recarregado)"""
        out = []
        for k, evs in grupos_d.items():
            evs = sorted(evs, key=lambda e: e["t"])
            atual = [evs[0]]
            for e in evs[1:]:
                if e["t"] - atual[-1]["t"] > 2.0:
                    out.append((k, atual))
                    atual = []
                atual.append(e)
            out.append((k, atual))
        out.sort(key=lambda kv: kv[1][0]["t"])
        return out

    for chave, evs in fatiar(efeitos_grupos):
        t = min(e["t"] for e in evs)
        e0 = evs[0]
        m = e0.get("mudanca")
        it = item_curto(e0.get("item"))
        ef = nome_efeito(e0.get("efeito"))
        cat = cat_efeito(e0)
        pausa = " (mudou durante a pausa)" if any(e.get("apos_pausa") for e in evs) else ""
        desf = [e for e in evs if e.get("_desfaz") is not None]
        refe = [e for e in evs if e.get("_refaz") is not None]
        evs_n = [e for e in evs if e.get("_desfaz") is None and e.get("_refaz") is None]
        for e in desf:
            o = e["_desfaz"]
            linha_desfez(e, textos_ev.get(id(o), "o ajuste em %s" % it), o["t"])
        for e in refe:
            o = e["_refaz"]
            linha_refez(e, textos_ev.get(id(o), "o ajuste em %s" % it), o["t"])
        if not evs_n:
            continue
        if m == "param":
            partes = []
            for e in evs_n:
                p = e.get("param") or {}
                partes.append("%s %s -> %s" % (nome_param(p), valor_param_txt(e.get("efeito"), p.get("antes")),
                                               valor_param_txt(e.get("efeito"), p.get("depois"))))
                textos_ev[id(e)] = "AJUSTE - %s %s: %s" % (it, ef, partes[-1])
                partes[-1] += volta(e)
                if p.get("depois") is None:
                    conferir.append((e["t"], "%s %s: '%s' com valor que o Premiere não deixa ler" % (it, ef, nome_param(p))))
            mostra = partes[:6]
            extra = " e mais %d" % (len(partes) - 6) if len(partes) > 6 else ""
            txt = "%s %s: %s%s%s" % (it, ef, "; ".join(mostra), extra, pausa)
            rot = "AJUSTE"
            contagem["ajustes"] += len(evs_n)
            ajuste_clipes.add((e0.get("item") or {}).get("faixa", "") + str((e0.get("item") or {}).get("inicio")))
            ajuste_cat[cat] = ajuste_cat.get(cat, 0) + len(evs_n)
        elif m == "keyframe":
            partes = []
            for e in evs_n:
                p = e.get("param") or {}
                partes.append("%s: %s -> %s keyframes%s" % (nome_param(p), p.get("antes_n") or 0, p.get("depois_n") or 0,
                                                            tempos_keyframe(e.get("item"), e.get("efeito"), p)))
            txt = "%s %s/%s%s%s" % (it, ef, "; ".join(partes), pausa, volta(evs_n[0]))
            rot = "KEYFRAME"
            contagem["keyframes"] += len(evs_n)
        elif m in ("colocou", "tirou"):
            via = " (arrastou do painel Efeitos)" if any(e.get("via") for e in evs_n) else ""
            ded = " (deduzido: último efeito da cadeia)" if any(e.get("deducao") for e in evs_n) else ""
            if m == "colocou":
                txt = "colocou %s em %s%s%s%s%s" % (ef, it, via, ded, pausa, volta(evs_n[0]))
                contagem["ef_colocou"] += len(evs_n)
            else:
                txt = "tirou %s de %s%s%s" % (ef, it, pausa, volta(evs_n[0]))
                contagem["ef_tirou"] += len(evs_n)
            rot = "EFEITO"
        elif m == "estado":
            efs = ", ".join(nome_efeito(x) for x in (e0.get("efeitos") or []))
            txt = "mexeu nos efeitos de %s (não havia leitura antes pra comparar; efeitos agora: %s)" % (it, efs or "?")
            rot = "EFEITO"
            conferir.append((t, "efeitos de %s: o que mudou exatamente (sem leitura anterior)" % it))
        elif m == "varios":
            txt = "%s: %d mudanças de uma vez (preset ou colar atributos?)" % (it, e0.get("total") or 0)
            rot = "AJUSTE"
        else:
            continue
        for e in evs_n:
            if id(e) not in textos_ev:
                textos_ev[id(e)] = "%s - %s" % (rot, txt)
        linhas.append((t, O_MUDANCA, "%s - %s" % (rot, txt)))
        decide(t, "%s - %s" % (rot, txt), cat, evs_n)

    # ---- projeto (varios "importou" da mesma leitura viram UMA linha)
    REAPARECE = ("importou", "criou_bin", "criou_sequencia", "novo")
    for leit, evs in fatiar(projetos_grupos):
        t = min(e["t"] for e in evs)
        pausa = "(mudou durante a pausa) " if any(e.get("apos_pausa") for e in evs) else ""
        imp = [e for e in evs if e.get("mudanca") == "importou" and e.get("_desfaz") is None and e.get("_refaz") is None
               and e.get("_volta") is None]
        if imp:
            bins = sorted(set((e.get("item") or {}).get("bin") or "(raiz)" for e in imp))
            nomes = [(e.get("item") or {}).get("nome") or "?" for e in imp]
            onde = (" pro bin '%s'" % bins[0]) if len(bins) == 1 and bins[0] != "(raiz)" else (" (bins: %s)" % ", ".join(bins) if len(bins) > 1 else "")
            txt = "%simportou %d arquivo%s%s: %s%s" % (pausa, len(imp), "s" if len(imp) > 1 else "", onde, ", ".join(nomes[:8]),
                                                       " e mais %d" % (len(nomes) - 8) if len(nomes) > 8 else "")
            contagem["pj_importou"] += len(imp)
            for e in imp:
                textos_ev[id(e)] = "importou %s" % (e.get("item") or {}).get("nome")
            linhas.append((t, O_MUDANCA, "PROJETO - " + txt))
            decide(t, "PROJETO - " + txt, "projeto", imp)
        for e in evs:
            if e in imp:
                continue
            txt = texto_projeto_um(e)
            textos_ev[id(e)] = txt
            if e.get("mudanca") in REAPARECE and e.get("_volta") is not None:
                # Ctrl+Z (ou desfazer a mao) de um "apagou": o item VOLTOU, nao foi importado (REVISAO-resumo 6)
                it_ = e.get("item") or {}
                art = TIPO_PROJ.get(it_.get("tipo"), "")
                quem = ("%s '%s'" % (art, it_.get("nome") or "?")) if art else (it_.get("nome") or "?")
                dentro = (" (com %d itens dentro)" % e["conteudo"]) if e.get("conteudo") else ""
                txt = "voltou pro projeto: %s%s%s" % (quem, dentro, volta(e))
                textos_ev[id(e)] = txt
                linhas.append((e["t"], O_MUDANCA, "PROJETO - " + pausa + txt))
                continue
            if e.get("_desfaz") is not None:
                linha_desfez(e, "PROJETO - " + textos_ev.get(id(e["_desfaz"]), "o projeto"), e["_desfaz"]["t"])
                continue
            if e.get("_refaz") is not None:
                linha_refez(e, textos_ev.get(id(e["_refaz"]), txt), e["_refaz"]["t"])
                continue
            m = e.get("mudanca")
            chave = {"criou_bin": "pj_bin", "criou_sequencia": "pj_seq", "renomeou": "pj_renomeou", "moveu": "pj_moveu", "apagou": "pj_apagou"}.get(m, "pj_outro")
            contagem[chave] += 1
            txt += volta(e)
            linhas.append((e["t"], O_MUDANCA, "PROJETO - " + pausa + txt))
            decide(e["t"], "PROJETO - " + pausa + txt, "projeto", [e])

    # pausas
    apagados = {p.get("n"): p for p in meta.get("pedacos_apagados") or []}
    citados = set()

    def txt_apagados(ns):
        return " · aqui ele APAGOU o %s" % ", o ".join("pedaço %s (%s)" % (n, dur((apagados.get(n) or {}).get("dur"))) for n in ns)
    for i, pa in enumerate(meta.get("pausas") or []):
        parado = (pa.get("fim") or pa.get("inicio") or 0) - (pa.get("inicio") or 0)
        ns = [n for n in pa.get("pedacos_apagados") or []]
        citados.update(ns)
        extra = txt_apagados(ns) if ns else ""
        if ns:
            parado -= sum((apagados.get(n) or {}).get("dur") or 0 for n in ns)    # o pedaco apagado nao e tempo parado
        if pa.get("queda"):
            linhas.append((pa.get("t_gravacao") or 0, O_PAUSA, "---- pausa %d: o servidor caiu aqui e a sessão voltou pausada (%s parado)%s ----" % (i + 1, dur(parado), extra)))
        else:
            linhas.append((pa.get("t_gravacao") or 0, O_PAUSA, "---- pausa %d (%s parado)%s ----" % (i + 1, dur(parado), extra)))
    # 0.3.0: pedaco apagado no comeco ou no fim (sem pausa em volta)
    for n, p in sorted(apagados.items(), key=lambda kv: (kv[1].get("cortado_em") or 0, kv[0] or 0)):
        if n not in citados:
            linhas.append((p.get("cortado_em") or 0, O_PAUSA, "---- pedaço %s apagado por ele aqui (%s fora da gravação) ----" % (n, dur(p.get("dur")))))

    # som do PC (14/10): troca de saida (fone Bluetooth conectou etc.) e gravador que caiu, no segundo em que foi
    for p in meta.get("partes") or []:
        for e in p.get("pc_eventos") or []:
            if e.get("o_que") == "trocou" or (e.get("o_que") in ("erro", "aviso") and p.get("pc_segmentos")):
                linhas.append((e.get("t_gravacao") or 0, O_PAINEL, "SOM DO PC - %s" % (e.get("msg") or e.get("o_que"))))
        if p.get("pc_caiu_em") and p.get("inicio"):
            linhas.append(((p.get("t0") or 0) + p["pc_caiu_em"] - p["inicio"], O_PAINEL,
                           "SOM DO PC - o gravador do som do PC parou aqui (o resto da parte ficou em silêncio no pc.wav)"))

    linhas.sort(key=lambda x: (x[0], x[1]))

    # ---------------------------------------------------------- cabecalho
    def data(ts):
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S") if ts else "?"

    t_total = meta.get("t_gravado")
    if t_total is None:
        t_total = max([e["t"] for e in eventos] or [0])
    partes = meta.get("partes") or []
    falhas_mic = []
    for p in partes:
        if p.get("mic_ok"):
            continue
        if p.get("mic_caiu_em") and p.get("inicio"):
            # o resto da parte e silencio no audio.wav (o alinhamento poe o buraco no fim)
            falhas_mic.append("%d (parou em %s)" % (p["n"], rec((p.get("t0") or 0) + p["mic_caiu_em"] - p["inicio"])))
        else:
            falhas_mic.append(str(p["n"]))
    saidas = meta.get("saidas") or {}
    seq = meta.get("sequencia") or "(sem sequência)"
    out = []
    out.append("# KAKASHI - correção de %s" % seq)   # nome na tela = KAKASHI (14/10); por dentro continua CORRETOR
    out.append("")
    out.append("- projeto: %s%s" % (meta.get("projeto") or "?", (" (%s)" % meta.get("projeto_caminho")) if meta.get("projeto_caminho") else ""))
    out.append("- sequência ao iniciar: %s" % seq)
    out.append("- relógio: %s -> %s" % (data(meta.get("inicio")), data(meta.get("fim"))))
    pedacos_fora = sorted(meta.get("pedacos_apagados") or [], key=lambda p: p.get("n") or 0)
    if pedacos_fora:
        out.append("- gravado: %s (pausas e pedaços apagados tirados) · %d pausa(s) · %d parte(s) que ficaram de %d" % (
            dur(t_total), len(meta.get("pausas") or []), len(partes), len(partes) + len(pedacos_fora)))
        for p in pedacos_fora:
            out.append("- pedaço %s apagado por ele (%s, que ficava em %s; %d evento(s) tirados) - fora do audio.wav, pc.wav, "
                       "tela.mp4, da linha do tempo e dos totais; arquivos e eventos guardados em _pedacos_apagados\\" % (
                           p.get("n"), dur(p.get("dur")), rec(p.get("cortado_em") or 0), p.get("eventos_tirados") or 0))
        if not partes:
            out.append("- ATENÇÃO: ele apagou TODOS os pedaços: nada desta sessão vale")
    else:
        out.append("- gravado: %s (pausas tiradas) · %d pausa(s) · %d parte(s)" % (dur(t_total), len(meta.get("pausas") or []), len(partes)))
    mic = meta.get("dispositivo") or "nenhum"
    out.append("- microfone: %s - %s" % (mic, "ok" if not falhas_mic else "FALHOU na(s) parte(s) %s" % ", ".join(falhas_mic)))
    linha_pc, sinal_pc = texto_som_pc(meta, partes, saidas)
    if linha_pc:
        out.append(linha_pc)
    arqs = []
    if saidas.get("audio"):
        arqs.append(("audio.wav = voz dele (microfone, %s)" if saidas.get("pc") else "audio.wav (%s)") % dur(saidas.get("audio_dur")))
    if saidas.get("pc"):
        arqs.append("pc.wav = som do PC (%s, %s)" % (dur(saidas.get("pc_dur")), sinal_pc))
    if saidas.get("tela"):
        arqs.append("tela.mp4 (%s, %s quadros/s)" % (dur(saidas.get("tela_dur")), meta.get("tela_fps") or 5))
    arqs.append("eventos.jsonl (%d eventos)" % len(eventos))
    out.append("- arquivos: " + ", ".join(arqs))
    ver = (painel_ver or (meta.get("painel_versao") or "")).replace("painel ", "").replace("corretor ", "").strip()
    if ver:
        out.append("- versões: painel %s · servidor %s" % (ver, meta.get("versao") or "?"))
    if capac:
        out.append("- o Premiere deixou ver: " + texto_capacidades(capac))
        falhas = sorted(k for k, v in (capac.get("leituras") or {}).items() if str(v).startswith("erro"))
        if falhas:
            out.append("- NÃO deixou ler (só a tela): " + "; ".join("%s (%s)" % (k, str(capac["leituras"][k])[6:80]) for k in falhas))
    if desemp:
        lacos = desemp.get("lacos") or {}
        pesado = sorted(lacos.items(), key=lambda kv: -(kv[1].get("total_ms") or 0))[:3]
        out.append("- leitura do Premiere: %d%% do tempo em média, pico %d%% (%s)%s · mais pesados: %s" % (
            int(round((desemp.get("ocupacao_media") or 0) * 100)), int(round((desemp.get("ocupacao_pico") or 0) * 100)),
            desemp.get("pico_laco") or "?", (" · %d leitura(s) acima de 3 s" % desemp["travas"]) if desemp.get("travas") else "",
            ", ".join("%s %s ms em média (pico %s)" % (k, num(v.get("media_ms") or 0, 1), v.get("pico_ms")) for k, v in pesado) or "-"))
    if meta.get("recuperada"):
        out.append("- ATENÇÃO: o servidor caiu no meio; esta sessão foi fechada depois pelo que estava no disco")
    for q in meta.get("quedas") or []:
        out.append("- ATENÇÃO: o servidor caiu em %s; a sessão voltou pausada e seguiu (fim da parte estimado pelo disco; partes parteNN/telaNN%s mantidas)" % (
            rec(q.get("t_gravacao") or 0), "/pcNN" if meta.get("gravar_som_pc") else ""))
    out.append("")
    out.append("Como ler: [mm:ss.s] = segundo da gravação = mesmo segundo do audio.wav%s e do tela.mp4 (pausas tiradas%s)."
               % (", do pc.wav" if saidas.get("pc") else "", " e pedaços apagados tirados" if pedacos_fora else ""))
    out.append("Tempos da timeline em h:mm:ss,ss = segundos desde o começo da sequência. "
               "Keyframe: o Premiere dá o tempo na MÍDIA; \"(na timeline: ...)\" = convertido pelo in do clipe; "
               "\"(tempo na mídia, não na timeline: ...)\" = não deu pra converter (velocidade diferente de 100% ou fora do trecho). "
               "Volume em dB como no Controle de Efeitos (o Premiere entrega em amplitude: 0 dB = 0,1778).")
    if zeros:
        out.append("Ponto zero da(s) sequência(s) (o Premiere pode mostrar o timecode somado a isto): " +
                   ", ".join("%s = %s" % (k, tl(v)) for k, v in zeros.items()))
    out.append("A fala dele está no audio.wav (transcrever e casar pelos [mm:ss.s]).")
    if saidas.get("pc"):
        out.append("Duas trilhas de som SEPARADAS, no mesmo relógio: audio.wav = só o microfone (a voz dele); "
                   "pc.wav = só o que saiu no som do PC (o que ele estava ouvindo: a timeline tocando, vídeo, música, aviso do Windows). "
                   "Pra saber o que ele ouvia quando falou ou mexeu, ouvir o pc.wav no mesmo [mm:ss.s]. "
                   "pc.wav em silêncio = nada tocando no PC naquele trecho. "
                   "Com caixa de som (sem fone), o microfone também pega um pouco do PC: o que está nos dois arquivos é do PC, não fala dele.")
    out.append("")
    out.append("## Linha do tempo")
    out.append("")
    for t, _, txt in linhas:
        out.append("%s %s" % (rec(t), txt))
    if not linhas:
        out.append("(nenhum evento)")

    # ---------------------------------------------------------- totais
    plays = [m for m in movs if m["tipo"] == "play"]
    assistindo = sum(m.get("dur", 0) for m in plays)
    revisoes = sum(1 for m in plays if m.get("revisao"))
    c = contagem
    out.append("")
    out.append("## Totais")
    out.append("")
    out.append("- tempo gravado: %s" % dur(t_total))
    out.append("- tempo assistindo (play): %s em %d trechos, %d revisão(ões)" % (dur(assistindo), len(plays), revisoes))
    out.append("- cortes (razor): %d" % c["corte"])
    out.append("- trims (início/fim): %d" % c["trim"])
    out.append("- apagados: %d" % c["apagou"])
    out.append("- colocados novos: %d" % c["novo"])
    out.append("- movidos: %d · slips: %d · liga/desliga: %d · outros: %d" % (c["moveu"], c["slip"], c["ligado"], c["outro"]))
    out.append("- ripples (consequências): %d · marcadores: %d (%d na sequência, %d em clipes) · mudanças de seleção: %d" % (
        c["ripple"], c["marcador"], c["marcador_seq"], c["marcador_clipe"], c["selecao"]))
    cats = ", ".join("%s %d" % (ROTULO_CAT.get(k, k), v) for k, v in sorted(ajuste_cat.items(), key=lambda kv: -kv[1]))
    out.append("- efeitos: %d colocados, %d tirados · ajustes: %d em %d clipe(s)%s · keyframes: %d · velocidade: %d" % (
        c["ef_colocou"], c["ef_tirou"], c["ajustes"], len(ajuste_clipes), (" (" + cats + ")") if cats else "", c["keyframes"], c["velocidade"]))
    out.append("- transições: %d colocadas, %d tiradas, %d mudaram de duração, %d trocadas" % (c["tr_colocou"], c["tr_tirou"], c["tr_duracao"], c["tr_trocou"]))
    out.append("- faixas: %d mutes/desmutes · %d nova(s) · %d apagada(s) · %d renomeada(s) · %d mexida(s) no cadeado" % (
        c["fx_mute"], c["fx_nova"], c["fx_apagada"], c["fx_renomeou"], c["fx_trava"]))
    out.append("- textos: %d editados · legendas: %d novas, %d apagadas, %d mudaram" % (c["textos"], c.get("leg_nova", 0), c.get("leg_apagada", 0), c.get("leg_mudou", 0)))
    out.append("- projeto: %d importados · %d bin(s) criado(s) · %d sequência(s) criada(s) · %d renomeados · %d movidos · %d apagados" % (
        c["pj_importou"], c["pj_bin"], c["pj_seq"], c["pj_renomeou"], c["pj_moveu"], c["pj_apagou"]))
    out.append("- exports: %d (%d Premiere, %d Media Encoder)" % (c["exp_premiere"] + c["exp_ame"], c["exp_premiere"], c["exp_ame"]))
    out.append("- desfeitos (prováveis): %d · refeitos: %d · voltas ao estado anterior (Ctrl+Z ou à mão): %d" % (c["desfez"], c["refez"], c["voltas"]))

    # ---------------------------------------------------------- decisoes
    out.append("")
    out.append("## Decisões (cada mudança + o que ele estava vendo nos %d s antes)" % CONTEXTO_S)
    out.append("")
    if not decisoes:
        out.append("(nenhuma mudança na timeline)")
    decisoes.sort(key=lambda x: x[0])
    for i, (t, txt, cat, refs) in enumerate(decisoes, 1):
        out.append("%d. %s (%s) %s%s" % (i, rec(t), cat, txt, marca_decisao(refs)))
        out.append("   antes: " + contexto(t, movs, selecoes, contexto_evs))

    # ---------------------------------------------------------- pra conferir na tela
    out.append("")
    out.append("## Pra conferir na tela (tela.mp4 no segundo indicado)")
    out.append("")
    conferir.sort(key=lambda x: x[0])
    vistos = set()
    for t, txt in conferir:
        if (round(t, 1), txt) in vistos:
            continue
        vistos.add((round(t, 1), txt))
        out.append("- %s %s" % (rec(t), txt))
    if not conferir:
        out.append("- (nada específico desta sessão)")
    out.append("- sempre só na tela: teclas apertadas, menus, cliques em painel, solo, faixa-alvo, sync lock, render de prévia (Enter), "
               "texto de legenda e (no Premiere 26.5.2) o texto de gráficos.")
    out.append("")
    return "\n".join(out)


def legendas_txt(lei):
    tempos, cont = lei.get("legendas (tempos)"), lei.get("legendas (contagem)")
    if tempos is not None and str(tempos).startswith("ok"):
        return "ok"
    if cont is None:
        return "não testado"
    if str(cont).startswith("ok") and "sempre 0" not in str(cont):
        return "ok"
    if "sempre 0" in str(cont):
        return "não confirmada (o Premiere sempre devolveu 0 legendas)"
    return "NÃO"


def texto_capacidades(c):
    ouv = c.get("ouvintes") or {}
    lei = c.get("leituras") or {}
    ex = c.get("existe") or {}

    def ok_l(*chaves):
        for k in chaves:
            for kk, v in lei.items():
                if kk.startswith(k):
                    return "ok" if str(v).startswith("ok") else "NÃO"
        return "não testado"

    def ok_o(k):
        v = ouv.get(k)
        if v is None:
            return "não testado"
        return "ok" if str(v).startswith("ok") else "NÃO"
    partes = [
        "avisos do Premiere %s" % ("ok" if any(str(v).startswith("ok") for v in ouv.values()) else "NÃO"),
        "marcador de clipe %s" % ok_l("marcadores de clipe"),
        "efeitos %s" % ok_l("efeitos"),
        "velocidade %s" % ok_l("velocidade"),
        "transições %s" % ok_l("transi"),
        "mute %s" % ok_l("mute"),
        "trava %s" % ("só alternância" if ok_o("faixa_cadeado") == "ok" else ok_o("faixa_cadeado")),
        "projeto %s" % ok_l("projeto"),
        "export %s" % ("ok" if ok_o("export_premiere") == "ok" or ok_o("media_encoder_pronto") == "ok" else "NÃO"),
        "monitor de origem %s" % ok_l("monitor de origem"),
        "legendas %s" % legendas_txt(lei),
        # SONDA 14/10: no 26.5.2 nem o conteudo ("Texto de origem" = null) nem o nome do clipe ("Grafico") acompanham
        "texto %s" % ("ok (MOGRT)" if ex.get("MogrtText") else "NÃO (só na tela)"),
        "desfazer %s" % ("aviso direto" if isinstance(ex.get("desfazer"), list) else "por dedução"),
    ]
    return ", ".join(partes)


def contexto(t, movs, selecoes, extras=None):
    extras = extras or {}
    vistos = []
    for m in movs:
        if m["t_fim"] < t - CONTEXTO_S or m["t_ini"] > t:
            continue
        if m["tipo"] == "play":
            vistos.append(("reviu" if m.get("revisao") else "assistiu") + " %s-%s" % (tl(m["ini"]), tl(m["fim"])))
        elif m["tipo"] == "salto":
            vistos.append("pulou %s->%s" % (tl(m["ini"]), tl(m["fim"])))
        elif m["tipo"] == "passos":
            vistos.append("quadro a quadro %s->%s" % (tl(m["ini"]), tl(m["fim"])))
        elif m["tipo"] == "passo":
            vistos.append("ajuste %s->%s" % (tl(m["ini"]), tl(m["fim"])))
        elif m["tipo"] == "posicao":
            continue
        else:
            vistos.append("arrastou %s->%s" % (tl(m["ini"]), tl(m["fim"])))
    ultimo = None
    for m in movs:
        if m["t_ini"] <= t:
            ultimo = m
    sel = None
    sel_cheia = None
    for ts, e in selecoes:
        if ts <= t + 0.3:
            sel = e
            if e.get("itens") and ts >= t - CONTEXTO_S:
                sel_cheia = e
    partes = []
    partes.append("; ".join(vistos) if vistos else "agulha parada")
    if ultimo is not None:
        partes.append("agulha em %s" % tl(ultimo["fim"]))
    if sel is not None:
        txt = texto_selecao(sel).replace("selecionou ", "", 1)
        if not sel.get("itens"):
            txt = "nada" if sel_cheia is None else "nada agora (pouco antes: %s)" % texto_selecao(sel_cheia).replace("selecionou ", "", 1)
        partes.append("seleção: " + txt)
    fontes = [x for x in extras.get("fonte", []) if t - 30.0 <= x[0] <= t + 0.3]
    if fontes:
        partes.append("monitor de origem: %s" % fontes[-1][1])
    cliques = [x for x in extras.get("clique", []) if t - 30.0 <= x[0] <= t + 0.3]
    if cliques:
        partes.append("clicou no painel Projeto: %s" % ", ".join(cliques[-1][1][:3]))
    if any(t - CONTEXTO_S <= x <= t + 0.3 for x in extras.get("navalha", [])):
        partes.append("estava com a navalha")
    return " · ".join(partes)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = Path(sys.argv[1])
    txt = gerar(p)
    (p / "resumo.md").write_text(txt, encoding="utf-8")
    print(txt)
