/* CORRETOR - painel UXP do Premiere (v0.2.0, 14/10/2026 - "olho de Deus").
 * Na tela se chama KAKASHI (pedido do Luan 14/10: "o ninja que copia"); por dentro continua CORRETOR
 * (id do plugin, servidor, pastas, sessoes). O olho do topo anima pelo estado: ver "olho (KAKASHI)".
 *
 * O Luan corrige uma edicao feita pelo Claude. Este painel e o OLHO: enquanto grava,
 * registra o que ele faz no Premiere e manda em lotes pro servidor.py, que grava o
 * microfone + a tela de reserva e escreve o resumo.md no Concluir.
 *
 * DOIS OLHOS (v0.2):
 *  1. AVISOS do Premiere (ppro.EventManager): o Premiere avisa QUANDO e ONDE algo mudou
 *     (faixa mexida, efeito solto, importou, exportou, cadeado, selecao, sequencia ativa...).
 *     O ouvinte NUNCA le o Premiere: so anota numa "caderneta" e volta. Quem le e um laco.
 *  2. FOTOS (como no 0.1): leitura periodica com orcamento. Rede de seguranca de tudo que
 *     tem leitura (so trava de faixa e export dependem so de aviso).
 *
 * O que captura (SO gravando; pausado nao registra):
 *  - agulha ~180 ms (+ "tocando" inferido com velocidade ESTAVEL: arrasto nao vira play);
 *  - sequencia ativa; selecao (aviso + rede de 1 s);
 *  - FOTO da timeline: clipes (+ velocidade), transicoes, faixas (mute, nome, contagem com
 *    renumeracao quando entra faixa no meio), entrada/saida, contagem de legendas;
 *  - marcadores da sequencia E dos clipes (clipe-mestre) num laco rapido que roda tocando;
 *  - efeitos: leitura funda so do clipe atingido/selecionado (parametros, keyframes);
 *  - projeto: arvore de bins (importou, criou, apagou, renomeou, moveu) + clique no painel Projeto;
 *  - export (Premiere e fila do Media Encoder), monitor de origem, navalha, desfazer provavel;
 *  - evento `capacidades` (o que este Premiere deixou ver) e `desempenho` (quanto do tempo
 *    o painel passou lendo o Premiere).
 *
 * Orcamento: no maximo ~35% do tempo lendo (tempo em que PELO MENOS UM laco estava lendo, numa janela de
 * 2 s, contando o laco que ainda esta rodando - revisao 14/10); leituras de prioridade baixa so abaixo de
 * 20%, com a agulha parada e sem foto rodando. A foto obedece so a regra dela (4x o proprio tempo).
 *
 * SO LEITURA: nenhum create*Action, nenhum executeTransaction, nenhum lockedAccess.
 * Toda chamada nova esta em try: se nao existir nesta versao do Premiere, registra UMA vez
 * ("nao disponivel: X") e segue - o que ja funcionava no 0.1 nunca quebra por causa dela.
 *
 * Armadilhas do UXP (pagas no DUBX/GRADEX):
 *  - querySelectorAll com seletor descendente volta vazio: so getElementById aqui;
 *  - <button> nao pinta: botoes sao <div role="button">; estado desligado = classe .desligado;
 *  - getSelection e async; getTrackItems da faixa e sync no tipo mas pode vir Promise (aw());
 *  - cada leitura de item em try: um clipe estranho nao derruba a foto;
 *  - displayName de parametro chegou com acento corrompido no GRADEX: consertar() + idx + matchName. Na SONDA
 *    (14/10, Premiere 26.5.2) chegou CERTO ("Posição", "Nível"): o consertar() fica so de rede (nao mexe em texto certo);
 *  - avisos do EventManager chegam com Object.keys VAZIO (como os objetos nativos de faixa/clipe): ler campo direto,
 *    sempre em try, e ter plano sem ele (SONDA 14/10).
 *
 * 0.3.0 (15/10, pedido do Luan: "coloca um botão de cancelar ... coloca nessas pausas de cada correção ... os pedacinhos
 * ali que você gravou. E se você quiser, você pode apagar um ou outro também"):
 *  - TRILHO: mini timeline embaixo do relogio. Cada pedaco (cada Pausar fecha um) e um bloco do tamanho da duracao,
 *    separados por um corte tracejado; o que esta gravando cresce na ponta. Clique no bloco = seleciona; o botao
 *    pequeno do lado vira "APAGAR N" (o servidor tira o pedaco da juncao e move os arquivos pra _pedacos_apagados).
 *    Pedaco apagado fica no trilho apagadinho: clicar nele e "VOLTAR N" desfaz (regra dele: nada de caixa de
 *    confirmacao, o desfazer e a rede).
 *  - CANCELAR: joga fora a sessao inteira (gravando ou pausada), sem resumo; a pasta vai pra sessoes\_descartadas
 *    (nunca apaga). Contra clique sem querer: 1o clique arma ("DE NOVO?", 3 s), 2o clique cancela.
 *  - Rotulos novos em letra miuda pixel montada letra por letra (pixelTexto, icones/px/c_*.png).
 *  - Relogio mostra o tempo que VALE (sem os pedacos apagados): campo t_valendo do /status.
 */
const ppro = require("premierepro");

const VERSAO = "0.3.0";
/* 7815 = o CORRETOR vivo. 7816 = a copia de desenvolvimento (CORRETOR DEV). Mudar aqui = mudar
 * no servidor.py e no ligar.ps1. O simulador troca esta linha e ABORTA se a troca falhar. */
const PORTA = 7815;
const BASES = ["http://127.0.0.1:" + PORTA, "http://localhost:" + PORTA];
/* identifica ESTA carga do painel: o numero da foto volta a 1 se o painel recarregar, e o
 * resumo.py agrupa uma leitura por (seq_id, carga, foto) */
const CARGA = Date.now();
let base = 0;

const T_AGULHA = 180;
const T_SEL_REDE = 1000;          // rede de seguranca da selecao quando o aviso SELECTION_CHANGED JA CHEGOU
const T_SEL_SEM_AVISO = 250;      // sem o aviso (ou ele nunca chegou): igual ao 0.1
const T_SEL_MIN = 250;            // nunca le a selecao mais de 1x a cada 250 ms (arrasto de selecao = rajada)
const SEL_SILENCIO = 150;         // com aviso: le 150 ms depois do ULTIMO aviso (ou 600 ms depois do 1o)
const T_MARCADORES = 500;         // marcador no beat com a musica tocando
const T_MARCADORES_SEQ_GRANDE = 2000;
const T_FOTO_MIN = 1000;
const T_FOTO_MIN_ACORDADA = 300;  // aviso de faixa acorda a foto antes do 1 s (respeitando os 25%)
const OCUPACAO_FOTO = 4;          // intervalo da foto >= 4x o tempo de leitura = no maximo 25% do tempo lendo
const T_FOTO_TOCANDO = 10000;     // agulha tocando = ninguem editando: foto no maximo a cada 10 s
const FOTO_BARATA_MS = 150;       // ... exceto foto barata acordada por aviso (Ctrl+K no beat): 1 a cada 2 s
const SILENCIO_MS = 400;          // rajada de avisos (slider do Lumetri): le depois de 400 ms sem aviso novo
const RAJADA_MAX_MS = 1500;       // ... ou depois de 1,5 s de rajada continua
const T_EFEITOS_SEL = 2000;       // clipe selecionado, aviso de faixa NUNCA chegou: leitura funda a cada 2 s
const T_EFEITOS_SEL_COM_AVISO = 15000;   // com o aviso de faixa funcionando, a rede do selecionado so a cada 15 s
const T_FUNDA_MAX = 150;          // leitura funda para depois de 150 ms (o resto do clipe fica pra proxima)
const MAX_FUNDAS_POR_S = 3;
const T_FUNDO = 2000;             // varredura de fundo (efeitos de todos os clipes, marcadores, legendas)
const FUNDO_CLIPES_POR_VOLTA = 20;
const FUNDO_MESTRES_POR_VOLTA = 10;
const T_PROJ_SEGURANCA = 15000;
/* SONDA 14/10 (Premiere 26.5.2): o DIRTY dispara a CADA mudanca (43 vezes na sonda, 1,5 s entre travar e destravar
 * sem salvar no meio) -> a seguranca da arvore barata volta pros 15 s (era 3 s quando se achava que so a 1a avisava) */
const T_PROJ_BARATO = 15000;      // arvore que le em <= 30 ms: seguranca a cada 15 s (prioridade media)
const PROJ_BARATO_MS = 30;
const T_PROJ_LENTO = 60000;
const T_PROJ_CLIQUE = 2000;
const JANELA_CLIQUE = 30000;
const T_LEGENDAS = 10000;         // contagem de legendas e posicoes: a cada 10 s (nao a cada foto)
const T_LEG_MAX = 100;            // posicoes das legendas: em lotes, parando em 100 ms (continua na volta seguinte)
const T_MARC_VOLTA_MAX = 40;      // marcadores de clipes-mestre: no maximo ~40 ms por volta (o resto na seguinte)
const T_FONTE = 1000;
const T_EVENTOS = 120;
const TETO = 0.35;                // soma de todos os lacos
const TETO_BAIXA = 0.20;          // prioridade baixa so abaixo disso (e parado)
const T_ENVIO = 1000;
const T_COMANDO = 500;
const MAX_SEL = 40;
const MAX_FILA = 50000;
const AUDIO_GUID = "80b8e3d5-6dca-4195-aefb-cb5f407ab009";   // getMediaType() de item de audio (medido)

/* ------------------------------------------------------------ elementos */
function el(id) { return document.getElementById(id); }
const btPrincipal = el("btPrincipal");
const btConcluir = el("btConcluir");
const elCrono = el("crono");
const elStatus = el("status");
const elAviso = el("aviso");
const elPonto = el("ponto");
const elLogo = el("logo");
const elSubLogo = el("sublogo");
const elOlho = el("olhoImg");
const elTrilho = el("trilho");          // 0.3.0: mini timeline dos pedacos
const btPedaco = el("btPedaco");        // 0.3.0: APAGAR / VOLTAR o pedaco selecionado
const btCancelar = el("btCancelar");    // 0.3.0: jogar fora a sessao (2 cliques)

/* ------------------------------------------------------------ estado (0.1) */
let servidor = null;          // ultimo /status (vem junto do GET /comando)
let tRecebido = 0;            // Date.now() de quando o status chegou (cronometro interpola)
let conectado = false;
let ocupado = false;          // um clique/comando em andamento
let capturando = false;
let geracao = 0;              // cada comecar/parar mata os lacos antigos
let fila = [];                // eventos ainda nao entregues
let perdidos = 0;             // eventos descartados por fila cheia (avisados depois)
let enviando = false;
let atual = null;             // {seq, seqId, nome, projNome, projCaminho, proj}
let fotoRodando = false;
let fotoN = 0;
let fimUltimaFoto = 0;
let fotoProxima = 0;          // Date.now() a partir de quando a proxima foto pode rodar (regra dos 25%)
let fotoMinima = 0;           // idem, quando um aviso de faixa acordou a foto
let fotoAcordada = 0;
let ultimaFotoMs = 0;         // quanto a ultima foto levou (foto barata pode rodar tocando, se acordada)
let avisouLenta = false;
let aposPausa = false;
let retomadaPendente = false;
let ultimaRetomada = 0;
let ag = null;                // ultima amostra da agulha {pos, ms}
let velAnt = null;            // velocidade da amostra anterior (play = velocidade estavel)
let agEmitida = null;         // ultima agulha MANDADA {pos, seqId}
let selSig = null;
let selBarata = null;         // assinatura barata da selecao (quantidade + inicio/fim/faixa)
let tocandoAgora = false;     // ultima amostra da agulha parecia play
let caminhos = {};            // projectItem.getId() -> caminho da midia (quase nunca muda)
let mensagem = "";            // linha de baixo (erro / onde salvou)
let mensagemErro = false;
let portaOcupada = false;     // algo que NAO e o CORRETOR respondeu na PORTA
let pedSel = null;            // 0.3.0: numero do pedaco selecionado no trilho (null = nenhum)
let cancelArmado = 0;         // 0.3.0: Date.now() do 1o clique no CANCELAR (o 2o, em ate 3 s, cancela)
const T_CANCELAR_ARMADO = 3000;
let trilhoLogs = 0;           // 0.3.0: medidas do trilho mandadas pro painel.log (no maximo 12 por carga)

/* ------------------------------------------------------------ estado (0.2) */
let estadoSeq = {};           // seqId -> ultima foto ampliada {itens, faixas, trans, io, usos, objs}
let historico = {};           // seqId -> [{h, foto, ms}] (ultimas 30 assinaturas: desfazer provavel)
let marcasSeq = {};           // seqId -> {mapa, ms}
let marcasClipe = {};         // pid -> {mapa, ms}
let mestres = {};             // pid -> {pi, nome, caminho}
let ultimaMarcSeq = 0;
let rodizioMestres = 0;
let selMestres = [];          // pids dos clipes selecionados (ate 8)
let selObjs = [];             // [{it, rec}] dos selecionados (ate 4) - leitura funda de efeitos
let selSuja = 0;              // aviso SELECTION_CHANGED (o ultimo)
let selSujaPrimeiro = 0;      // o 1o aviso da rajada
let selInicio = 0;
let sujo = {};                // caderneta: rotulo da faixa -> {primeiro, ultimo, ini, fim, n, info}
let muteSujo = {};            // rotulo -> ms do aviso (leitura relampago do isMuted)
let ultimoAvisoFaixa = 0;
let avisosFaixa = [];         // instantes dos ultimos avisos de faixa (o DIRTY colado num deles = edicao de timeline)
let pendTrava = [];
let pendExport = [];
let pendFerramenta = [];
let pendDesfazer = [];
let pendClique = null;        // {ms, itens}
let ultimoCliqueSig = null;
let ultimaFerramenta = {};
let viaDrop = 0;              // EFFECT_DROP_COMPLETE (soltou efeito do painel)
let efCache = {};             // chaveClipe -> {comps, ms}
let efLista = {};             // chaveClipe -> [matchName] (varredura de fundo)
let efHist = {};              // chave|match|idx -> [{v, ms}] (desfazer provavel em efeito)
let ehTexto = {};             // chaveClipe -> true (cadeia com AE.ADBE Text / Capsule)
let fundaFila = [];           // leituras fundas pendentes {rec, it, origem, ini} (aviso de faixa / varredura)
let filaIni = [];             // 18/10: leituras de BASE (efeito_inicial) - fila propria, prioridade mais baixa que tudo
let filaIniVista = {};        // chaveClipe -> 1 (ja entrou na fila de base)
let ultimaIni = 0;            // ms da ultima leitura de base
let fundas = [];              // instantes das ultimas leituras fundas (teto por segundo)
let leituraEf = 0;
let ultimaFundaSel = 0;
let rodizioFundo = 0;
let ultimoFundo = 0;
let projFoto = null;          // {id: {id, nome, tipo, pai, bin}} do projeto ATIVO
let projChave = null;         // guid do projeto da projFoto (2 projetos abertos: uma foto por projeto)
let projEstados = {};         // guid -> {foto, seqIds, lento, ms} dos outros projetos abertos
let projDirty = 0;            // ultimo ProjectEvent.DIRTY
let projDirtyVisto = 0;       // DIRTY ja tratado (lido ou descartado por ser edicao de timeline)
let projSeqIds = null;        // {projectItemId: true} das sequencias
let projSujo = 0;
let projUltima = 0;
let projN = 0;
let projImport = null;        // {ms, estado}
let projLento = false;
let projMsLeitura = 0;        // quanto a ultima leitura da arvore levou (intervalo minimo = 4x isso)
let ultimoCliqueProj = 0;
let fonteAtual = null;        // id do item no monitor de origem
let ultimaFonte = 0;
let legPos = {};              // seqId -> {sig, lista, ms}
let legLeitura = null;        // leitura das posicoes das legendas em andamento {seqId, sig, j, k, lista}
let ultimaLeg = 0;
let ultimaContLeg = 0;        // ultima contagem de itens das faixas de legenda (dentro da foto)
let rodizioSelMestre = 0;
let encoderVistos = {};       // job|fase -> ms (os dois nomes de aviso do Media Encoder: nao conta 2x)
let encoderJobs = {};         // jobID -> ultimo quarto de progresso avisado
let capacEmitida = false;
let ouvintes = [];            // {alvo, nome, fn, chave, grupo}
let faixasLigadas = null;     // assinatura (seqId|nv|na) das faixas com ouvinte
let DES = null;               // desempenho

/* o que este Premiere deixou ver (vai no evento `capacidades`) */
let CAPAC = { ouvintes: {}, leituras: {}, existe: {}, campos: {}, disparos: {} };
const MARCAS = { vel: null, trans: null, mute: null, legendas: null, io: null, marcClipe: null, efeitos: null, projeto: null, fonte: null, selProj: null };

/* ------------------------------------------------------------ utilidades */
async function aw(x) { return (x && typeof x.then === "function") ? await x : x; }
async function tentar(f) { try { return { v: await aw(f()) }; } catch (e) { return { e: e }; } }
function seg(tt) { try { return (tt && tt.seconds !== undefined) ? Number(tt.seconds) : null; } catch (_) { return null; } }
function r3(x) { return (x === null || x === undefined || isNaN(x)) ? null : Math.round(x * 1000) / 1000; }
function r4(x) { return (x === null || x === undefined || isNaN(x)) ? null : Math.round(x * 10000) / 10000; }
/* entrada/saida da SEQUENCIA: sem nada marcado o Premiere 26.5.2 devolve -400000 s nas duas (MEDIDO na SONDA 14/10,
 * passo 0: "in=-400000 out=-400000 fim da sequencia=21.033"; passo 6, so a saida marcada: "in=-400000 out=5").
 * Negativo = nao marcado = null. (A suposicao antiga "sem saida o out = fim da sequencia" estava errada.) */
function tempoMarcado(tt) { const s = seg(tt); return (s === null || isNaN(s) || s < 0) ? null : r3(s); }
function msgErro(e) {
  if (e && e.message !== undefined) return e.message;
  try { return JSON.stringify(e); } catch (_) { return String(e); }
}
function dormir(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
function milhar(n) {
  const s = String(Math.max(0, Math.round(n || 0)));
  let out = "";
  for (let i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 === 0) out += ".";
    out += s[i];
  }
  return out;
}
function relogio(t) {
  t = Math.max(0, Math.floor(t || 0));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
}
function constante(grupo, nome, padrao) {
  try {
    const g = ppro.Constants && ppro.Constants[grupo];
    if (g && g[nome] !== undefined) return g[nome];
  } catch (_) {}
  return padrao;
}
function tipoClipe() { return constante("TrackItemType", "CLIP", 1); }
function tipoTransicao() { return constante("TrackItemType", "TRANSITION", 2); }
function str(x) { try { return String(x && x.toString ? x.toString() : x); } catch (_) { return ""; } }

/* displayName com acento corrompido (MEDIDO no GRADEX): "PosiÃ§Ã£o" -> "Posição".
 * So mexe se TODOS os caracteres forem < 256 e a sequencia for UTF-8 valida. */
function consertar(s) {
  s = s === null || s === undefined ? "" : String(s);
  if (!/[À-ÿ]/.test(s)) return s;
  const b = [];
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c > 255) return s;
    b.push(c);
  }
  let out = "", i = 0, mexeu = false;
  while (i < b.length) {
    const c = b[i];
    if (c < 0x80) { out += String.fromCharCode(c); i++; continue; }
    if ((c & 0xE0) === 0xC0 && i + 1 < b.length && (b[i + 1] & 0xC0) === 0x80) {
      out += String.fromCharCode(((c & 0x1F) << 6) | (b[i + 1] & 0x3F)); i += 2; mexeu = true; continue;
    }
    if ((c & 0xF0) === 0xE0 && i + 2 < b.length && (b[i + 1] & 0xC0) === 0x80 && (b[i + 2] & 0xC0) === 0x80) {
      out += String.fromCharCode(((c & 0x0F) << 12) | ((b[i + 1] & 0x3F) << 6) | (b[i + 2] & 0x3F)); i += 3; mexeu = true; continue;
    }
    return s;     // nao e UTF-8 lido como latin1: o texto ja estava certo
  }
  return mexeu ? out : s;
}

/* hash curto (FNV-1a 32 bits) pra guardar assinaturas de foto sem guardar a foto */
function hash(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return ("0000000" + h.toString(16)).slice(-8);
}

/* ------------------------------------------------------------ servidor */
async function chamar(rota, opcoes) {
  let ultimo;
  for (let n = 0; n < BASES.length; n++) {
    const b = BASES[(base + n) % BASES.length];
    try {
      const r = await fetch(b + rota, opcoes);
      base = (base + n) % BASES.length;
      return r;
    } catch (e) { ultimo = e; }
  }
  throw ultimo;
}

async function post(rota, obj) {
  const r = await chamar(rota, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj || {}) });
  return await r.json();
}

const LOGADOS = {};
function logar(nivel, msg) {
  if (nivel === "erro") { mensagem = msg; mensagemErro = true; pintar(); }
  const agora = Date.now();
  if (LOGADOS[msg] && agora - LOGADOS[msg] < 10000) return;     // mesmo erro em laco: 1 linha a cada 10 s
  LOGADOS[msg] = agora;
  try { console.log("[corretor] " + nivel + ": " + msg); } catch (_) {}
  post("/log", { nivel: nivel, msg: msg }).catch(function () {});
}

/* leitura nova que falhou: so desliga de vez se nunca deu certo e ja falhou `limite` vezes
 * (um clipe ou faixa estranho nao pode apagar a leitura da sessao inteira) */
function falhou(marca, limite) {
  MARCAS[marca + "Erros"] = (MARCAS[marca + "Erros"] || 0) + 1;
  if (!MARCAS[marca] && MARCAS[marca + "Erros"] >= limite) MARCAS[marca] = false;
}

/* chamada nova que nao existe/falhou nesta versao do Premiere: UMA linha no log e segue */
const AVISADOS = {};
function naoDisponivel(chave, e) {
  const ja = CAPAC.leituras[chave];
  if (ja !== undefined && String(ja).indexOf("ok") === 0) { if (ja === "ok") CAPAC.leituras[chave] = "ok (às vezes erro: " + msgErro(e) + ")"; }
  else CAPAC.leituras[chave] = "erro: " + msgErro(e);
  if (AVISADOS[chave]) return;
  AVISADOS[chave] = true;
  logar("aviso", "não disponível: " + chave + " (" + msgErro(e) + ")");
}
function leituraOk(chave) { if (CAPAC.leituras[chave] === undefined || String(CAPAC.leituras[chave]).indexOf("erro") === 0) CAPAC.leituras[chave] = "ok"; }

function empurrar(ev) {
  if (!ev.ms) ev.ms = Date.now();
  if (!ev.seq_id && atual) ev.seq_id = atual.seqId;
  fila.push(ev);
  if (fila.length > MAX_FILA) {
    const sobra = fila.length - MAX_FILA;
    fila.splice(0, sobra);
    perdidos += sobra;
    if (!AVISADOS.fila_cheia) { AVISADOS.fila_cheia = true; logar("aviso", "fila cheia: eventos mais antigos descartados (o servidor não está recebendo?)"); }
  }
}

async function enviar() {
  if (enviando || !fila.length) return true;
  enviando = true;
  const lote = fila.splice(0, 500);
  try {
    const r = await post("/eventos", { eventos: lote });
    /* "sem sessao" (servidor reiniciando / juntando) NAO e entregue: o lote volta pra fila.
     * Servidor que caiu no meio volta com a sessao PAUSADA e aceita; se ele estiver mesmo
     * parado, o lacoComando descarta a fila e avisa no log. */
    if (!r.ok) throw new Error(r.erro || "servidor recusou o lote");
    if (servidor) { servidor.eventos = r.eventos; }
    return true;
  } catch (e) {
    fila = lote.concat(fila);      // servidor caiu: guarda e manda depois
    return false;
  } finally {
    enviando = false;
  }
}

async function esvaziar() {
  for (let i = 0; i < 200 && fila.length; i++) {
    while (enviando) await dormir(30);
    if (!(await enviar())) return false;
  }
  return !fila.length;
}

/* ------------------------------------------------------------ desempenho (orcamento) */
/* Revisao 14/10 (REVISAO-api 9, REVISAO-desempenho 1): a ocupacao era a SOMA do tempo dos lacos e so contava
 * laco que ja tinha terminado. Lacos que esperam o Premiere juntos contavam a mesma espera 3-4 vezes, e o laco
 * que ainda estava lendo (a foto de 1-3 s numa timeline grande) nao contava nada. Agora: tempo em que PELO
 * MENOS UM laco estava lendo (contador de lacos ativos), incluindo o que ainda esta rodando. */
function zerarDesempenho() {
  DES = { capt_ms: 0, desde: capturando ? Date.now() : null, lacos: {}, pico: 0, picoLaco: null, ultimoLog: Date.now(), travas: 0,
          ativos: 0, ocupadoDesde: 0, ocupadoTotal: 0, periodos: [], lentoLog: {} };
}
zerarDesempenho();

function inicioLeitura(D) {
  if (!D) return;
  if (D.ativos === 0) D.ocupadoDesde = Date.now();
  D.ativos++;
}
function fimLeitura(D) {
  if (!D || D.ativos <= 0) return;
  D.ativos--;
  if (D.ativos === 0) {
    const agora = Date.now();
    D.ocupadoTotal += agora - D.ocupadoDesde;
    D.periodos.push([D.ocupadoDesde, agora]);
    while (D.periodos.length && D.periodos[0][1] < agora - 2000) D.periodos.shift();
  }
}

function registrar(nome, ms) {
  if (!DES) return;
  const L = DES.lacos[nome] || (DES.lacos[nome] = { voltas: 0, total: 0, pico: 0 });
  L.voltas++; L.total += ms; if (ms > L.pico) L.pico = ms;
  const oc = ocupacao();
  if (oc > DES.pico) { DES.pico = oc; DES.picoLaco = nome; }
  if (ms > 3000) DES.travas++;       // "trava" = uma volta de mais de 3 s
  /* leitura lenta: no maximo 1 linha por laco por minuto (o numero muda a cada vez e furava o filtro) */
  if (ms > 1000 && Date.now() - (DES.lentoLog[nome] || 0) >= 60000) {
    DES.lentoLog[nome] = Date.now();
    logar("aviso", "leitura lenta: laço '" + nome + "' levou " + (ms / 1000).toFixed(1) + " s (próximo aviso deste laço só daqui a 1 min)");
  }
}

function ocupacao() {
  if (!DES) return 0;
  const agora = Date.now(), ini = agora - 2000;
  let soma = 0;
  for (let i = 0; i < DES.periodos.length; i++) {
    const p = DES.periodos[i];
    if (p[1] > ini) soma += p[1] - Math.max(p[0], ini);
  }
  if (DES.ativos > 0) soma += agora - Math.max(DES.ocupadoDesde, ini);
  return Math.min(1, soma / 2000);
}

/* alta = sempre; media = abaixo do teto de 35%; baixa = abaixo de 20%, agulha parada e sem foto rodando */
function podeRodar(prio) {
  if (prio === "alta") return true;
  const oc = ocupacao();
  if (prio === "media") return oc < TETO;
  return oc < TETO_BAIXA && !tocandoAgora && !fotoRodando;
}

function resumoDesempenho() {
  const lacos = {};
  let total = 0;
  Object.keys(DES.lacos).forEach(function (k) {
    const L = DES.lacos[k];
    total += L.total;
    lacos[k] = { voltas: L.voltas, media_ms: Math.round(L.total / Math.max(1, L.voltas) * 10) / 10, pico_ms: L.pico, total_ms: L.total };
  });
  const capt = DES.capt_ms + (DES.desde ? Date.now() - DES.desde : 0);
  const ocupado = DES.ocupadoTotal + (DES.ativos > 0 ? Date.now() - DES.ocupadoDesde : 0);
  return { lacos: lacos, capturando_s: Math.round(capt / 100) / 10, ocupacao_media: capt > 0 ? Math.round(Math.min(ocupado, capt) / capt * 1000) / 1000 : 0,
           soma_lacos_ms: total, ocupado_ms: ocupado,
           ocupacao_pico: Math.round(DES.pico * 1000) / 1000, pico_laco: DES.picoLaco, travas: DES.travas };
}

/* ------------------------------------------------------------ ouvintes (avisos do Premiere) */
function nomeEvento(cands) {
  for (let i = 0; i < cands.length; i++) {
    try {
      const v = cands[i][1]();
      if (v !== undefined && v !== null && v !== "") return { v: v, rot: cands[i][0] };
    } catch (_) {}
  }
  return null;
}

function amostra(chave, ev) {
  CAPAC.disparos[chave] = (CAPAC.disparos[chave] || 0) + 1;
  if (CAPAC.campos[chave]) return;
  try {
    const campos = {};
    Object.keys(ev || {}).slice(0, 15).forEach(function (k) {
      let v = null;
      try { v = ev[k]; } catch (_) {}
      const t = typeof v;
      campos[k] = (t === "number" || t === "string" || t === "boolean") ? v : (v && v.seconds !== undefined ? "TickTime " + v.seconds : t);
    });
    CAPAC.campos[chave] = campos;
  } catch (_) { CAPAC.campos[chave] = "?"; }
}

function ouvir(chave, alvo, cands, fn, grupo, captura) {
  const n = nomeEvento(cands);
  if (!n) { if (!CAPAC.ouvintes[chave]) CAPAC.ouvintes[chave] = "nao existe"; return false; }
  const g = geracao;
  const embrulho = function (ev) {
    if (g !== geracao || !capturando) return;
    try { amostra(chave, ev); fn(ev); } catch (_) {}
  };
  if (!ppro.EventManager) {
    CAPAC.ouvintes[chave] = "nao existe (sem ppro.EventManager)";
    naoDisponivel("avisos do Premiere (ppro.EventManager)", new Error("ppro.EventManager nao existe"));
    return false;
  }
  try {
    if (alvo) {
      if (captura) ppro.EventManager.addEventListener(alvo, n.v, embrulho, true);
      else ppro.EventManager.addEventListener(alvo, n.v, embrulho);
    } else {
      if (captura) ppro.EventManager.addGlobalEventListener(n.v, embrulho, true);
      else ppro.EventManager.addGlobalEventListener(n.v, embrulho);
    }
    ouvintes.push({ alvo: alvo, nome: n.v, fn: embrulho, chave: chave, grupo: grupo || "global" });
    const atualC = CAPAC.ouvintes[chave];
    if (!atualC || String(atualC).indexOf("ok") !== 0) CAPAC.ouvintes[chave] = "ok (" + n.rot + ")";
    return true;
  } catch (e) {
    CAPAC.ouvintes[chave] = "erro: " + msgErro(e);
    naoDisponivel("ouvinte " + chave, e);
    return false;
  }
}

function calar(grupo) {
  const fica = [];
  for (let i = 0; i < ouvintes.length; i++) {
    const o = ouvintes[i];
    if (grupo && o.grupo !== grupo) { fica.push(o); continue; }
    try {
      if (o.alvo) ppro.EventManager.removeEventListener(o.alvo, o.nome, o.fn);
      else ppro.EventManager.removeGlobalEventListener(o.nome, o.fn);
    } catch (_) {}
  }
  ouvintes = fica;
  if (!grupo || grupo === "faixa") faixasLigadas = null;
}

function cand(rot, f) { return [rot, f]; }
function daConst(grupo, nome) { return function () { return ppro.Constants[grupo][nome]; }; }

async function ligarOuvintes(g) {
  const C = daConst;
  ouvir("sequencia_ativada", null, [cand("Constants.SequenceEvent.ACTIVATED", C("SequenceEvent", "ACTIVATED"))], function () {
    selSuja = Date.now(); projSujo = projSujo || Date.now();
  });
  ouvir("selecao_mudou", null, [cand("Constants.SequenceEvent.SELECTION_CHANGED", C("SequenceEvent", "SELECTION_CHANGED"))], function () {
    selSuja = Date.now();
    if (!selSujaPrimeiro) selSujaPrimeiro = selSuja;
  });
  /* avisos de PROJETO - MEDIDO na SONDA (14/10, Premiere 26.5.2), cada um ligado das duas formas:
   *  - DIRTY so chega COM captura (true): 43 vezes "com", 0 "sem";
   *  - PROJECT_ITEM_SELECTION_CHANGED so chega SEM captura: 20 vezes "sem", 0 "com".
   * Os de sequencia/operacao vao sem (chegaram assim na sonda). */
  ouvir("projeto_sujo", null, [cand("Constants.ProjectEvent.DIRTY", C("ProjectEvent", "DIRTY")),
                               cand("ProjectEvent.EVENT_DIRTY", function () { return ppro.ProjectEvent.EVENT_DIRTY; })],
        function () { projDirty = Date.now(); }, "global", true);
  ouvir("projeto_clique", null, [cand("Constants.ProjectEvent.PROJECT_ITEM_SELECTION_CHANGED", C("ProjectEvent", "PROJECT_ITEM_SELECTION_CHANGED"))],
        function (ev) {
          /* a sonda nao viu campo nenhum no aviso (Object.keys vazio, igual aos objetos nativos de faixa/clipe):
           * se projectItems nao vier, o passoEventos pergunta ao ProjectUtils.getSelection */
          let itens = null;
          try { itens = ev && ev.projectItems; } catch (_) {}
          pendClique = { ms: Date.now(), itens: itens };
          ultimoCliqueProj = Date.now();
        }, "global");
  ouvir("importou", null, [cand("Constants.OperationCompleteEvent.IMPORT_MEDIA_COMPLETE", C("OperationCompleteEvent", "IMPORT_MEDIA_COMPLETE")),
                           cand("OperationCompleteEvent.EVENT_IMPORT_MEDIA_COMPLETE", function () { return ppro.OperationCompleteEvent.EVENT_IMPORT_MEDIA_COMPLETE; })],
        function (ev) { let st = null; try { st = ev && ev.state; } catch (_) {} projImport = { ms: Date.now(), estado: st }; projSujo = Date.now(); });
  ouvir("export_premiere", null, [cand("Constants.OperationCompleteEvent.EXPORT_MEDIA_COMPLETE", C("OperationCompleteEvent", "EXPORT_MEDIA_COMPLETE")),
                                  cand("OperationCompleteEvent.EVENT_EXPORT_MEDIA_COMPLETE", function () { return ppro.OperationCompleteEvent.EVENT_EXPORT_MEDIA_COMPLETE; })],
        function (ev) { let st = null; try { st = ev && ev.state; } catch (_) {} pendExport.push({ ms: Date.now(), via: "premiere", fase: "pronto", estado: st }); });
  ouvir("efeito_solto", null, [cand("Constants.OperationCompleteEvent.EFFECT_DROP_COMPLETE", C("OperationCompleteEvent", "EFFECT_DROP_COMPLETE")),
                               cand("OperationCompleteEvent.EVENT_EFFECT_DROP_COMPLETE", function () { return ppro.OperationCompleteEvent.EVENT_EFFECT_DROP_COMPLETE; })],
        function () { viaDrop = Date.now(); });
  ouvir("limite_midia", null, [cand("Constants.OperationCompleteEvent.CLIP_EXTEND_REACHED", C("OperationCompleteEvent", "CLIP_EXTEND_REACHED")),
                               cand("OperationCompleteEvent.EVENT_CLIP_EXTEND_REACHED", function () { return ppro.OperationCompleteEvent.EVENT_CLIP_EXTEND_REACHED; })],
        function () { pendFerramenta.push({ ms: Date.now(), qual: "limite_da_midia" }); });
  ouvir("navalha_agulha", null, [cand("Constants.SnapEvent.RAZOR_PLAYHEAD", C("SnapEvent", "RAZOR_PLAYHEAD")),
                                 cand("SnapEvent.EVENT_SNAP_RAZOR_TO_PLAYHEAD", function () { return ppro.SnapEvent.EVENT_SNAP_RAZOR_TO_PLAYHEAD; })],
        function () { pendFerramenta.push({ ms: Date.now(), qual: "navalha" }); });
  ouvir("navalha_marcador", null, [cand("Constants.SnapEvent.RAZOR_MARKER", C("SnapEvent", "RAZOR_MARKER")),
                                   cand("SnapEvent.EVENT_SNAP_RAZOR_TO_MARKER", function () { return ppro.SnapEvent.EVENT_SNAP_RAZOR_TO_MARKER; })],
        function () { pendFerramenta.push({ ms: Date.now(), qual: "navalha" }); });

  /* fila do Media Encoder (os avisos trazem jobID e, no fim, os caminhos dos arquivos) */
  let em = null;
  try { em = ppro.EncoderManager ? await aw(ppro.EncoderManager.getManager()) : null; CAPAC.existe.EncoderManager = !!em; }
  catch (e) { CAPAC.existe.EncoderManager = "erro: " + msgErro(e); }
  if (g !== geracao || !capturando) return;
  if (em) {
    /* REVISAO-api 6: o exemplo oficial usa EncoderManager.EVENT_RENDER_* (e o tipo do addEventListener nem lista
     * EncoderEvent). Esse vem primeiro; se o Constants.EncoderEvent existir com OUTRO valor, liga os dois e o
     * passoEventos nao conta o mesmo aviso duas vezes (mesmo job + mesma fase). */
    const fases = [["RENDER_QUEUE", "EVENT_RENDER_QUEUE", "fila"], ["RENDER_PROGRESS", "EVENT_RENDER_PROGRESS", "progresso"],
                   ["RENDER_COMPLETE", "EVENT_RENDER_COMPLETE", "pronto"], ["RENDER_ERROR", "EVENT_RENDER_ERROR", "erro"],
                   ["RENDER_CANCEL", "EVENT_RENDER_CANCEL", "cancelado"]];
    fases.forEach(function (f) {
      const fn = function (ev) { pendExport.push(Object.assign({ ms: Date.now(), via: "media_encoder", fase: f[2] }, lerEventoEncoder(ev))); };
      let v1 = null, v2 = null;
      try { v1 = ppro.EncoderManager[f[1]]; } catch (_) {}
      try { v2 = ppro.Constants.EncoderEvent[f[0]]; } catch (_) {}
      const ligou = ouvir("media_encoder_" + f[2], em, [cand("EncoderManager." + f[1], function () { return ppro.EncoderManager[f[1]]; }),
                                                         cand("Constants.EncoderEvent." + f[0], C("EncoderEvent", f[0]))], fn);
      if (ligou && v1 !== null && v1 !== undefined && v2 !== null && v2 !== undefined && String(v1) !== String(v2))
        ouvir("media_encoder_" + f[2] + "_outro_nome", em, [cand("Constants.EncoderEvent." + f[0], C("EncoderEvent", f[0]))], fn);
    });
  }
  procurarDesfazer();
}

function lerEventoEncoder(ev) {
  const r = {};
  try { if (ev && ev.jobID !== undefined) r.job = str(ev.jobID); } catch (_) {}
  try { if (ev && ev.outputFiles) r.arquivos = [].concat(ev.outputFiles).map(str); } catch (_) {}
  try { if (ev && ev.progressAmount !== undefined) r.progresso = Number(ev.progressAmount); } catch (_) {}
  try { if (ev && ev.inErrorNumber !== undefined) r.erro_n = ev.inErrorNumber; } catch (_) {}
  return r;
}

/* Ctrl+Z: a API (26.3 / 26.5.1 / 27 beta) nao tem aviso de desfazer. Procura mesmo assim: se um
 * dia aparecer um nome com UNDO/REDO/HISTORY, liga um ouvinte direto. */
function procurarDesfazer() {
  const achados = [];
  try {
    Object.keys(ppro.Constants || {}).forEach(function (grupo) {
      const gr = ppro.Constants[grupo];
      const grupoCasa = /undo|redo|history/i.test(grupo);
      Object.keys(gr || {}).forEach(function (nome) {
        if (grupoCasa || /undo|redo/i.test(nome)) achados.push(["Constants." + grupo + "." + nome, gr[nome], nome]);
      });
    });
  } catch (_) {}
  try { Object.keys(ppro.EventManager || {}).forEach(function (k) { if (/undo|redo|history/i.test(k)) achados.push(["EventManager." + k, null, k]); }); } catch (_) {}
  try { Object.keys(ppro || {}).forEach(function (k) { if (/undo|history/i.test(k)) achados.push(["ppro." + k, null, k]); }); } catch (_) {}
  CAPAC.existe.desfazer = achados.length ? achados.map(function (a) { return a[0]; }) : "nao existe (deducao: desfazer_provavel)";
  achados.forEach(function (a) {
    if (a[1] === null || a[1] === undefined) return;
    const qual = /redo/i.test(a[2]) ? "refez" : "desfez";
    ouvir("desfazer:" + a[0], null, [cand(a[0], function () { return a[1]; })], function () { pendDesfazer.push({ ms: Date.now(), qual: qual, nome: a[0] }); });
  });
}

/* ouvintes por FAIXA (TRACK_CHANGED / INFO_CHANGED / LOCK_CHANGED): religados quando a sequencia
 * ativa troca ou o numero de faixas muda */
function ligarFaixas(seqId, trs) {
  const assin = seqId + "|" + trs.V.length + "|" + trs.A.length;
  if (assin === faixasLigadas || !capturando) return;
  calar("faixa");
  sujo = {}; muteSujo = {};
  ["V", "A"].forEach(function (tipo) {
    const grupoEv = tipo === "V" ? "VideoTrackEvent" : "AudioTrackEvent";
    const estatico = tipo === "V" ? "VideoTrack" : "AudioTrack";
    for (let i = 0; i < trs[tipo].length; i++) {
      const tr = trs[tipo][i];
      if (!tr) continue;
      const rot = tipo + (i + 1);
      ouvir("faixa_mudou", tr, [cand("Constants." + grupoEv + ".TRACK_CHANGED", daConst(grupoEv, "TRACK_CHANGED")),
                                cand(estatico + ".EVENT_TRACK_CHANGED", function () { return ppro[estatico].EVENT_TRACK_CHANGED; })],
            aoAvisoFaixa(rot, false), "faixa");
      ouvir("faixa_info", tr, [cand("Constants." + grupoEv + ".INFO_CHANGED", daConst(grupoEv, "INFO_CHANGED")),
                               cand(estatico + ".EVENT_TRACK_INFO_CHANGED", function () { return ppro[estatico].EVENT_TRACK_INFO_CHANGED; })],
            aoAvisoFaixa(rot, true), "faixa");
      ouvir("faixa_cadeado", tr, [cand("Constants." + grupoEv + ".LOCK_CHANGED", daConst(grupoEv, "LOCK_CHANGED")),
                                  cand(estatico + ".EVENT_TRACK_LOCK_CHANGED", function () { return ppro[estatico].EVENT_TRACK_LOCK_CHANGED; })],
            function () { pendTrava.push({ faixa: rot, ms: Date.now() }); }, "faixa");
    }
  });
  faixasLigadas = assin;
}

function aoAvisoFaixa(rot, info) {
  return function (ev) {
    const agora = Date.now();
    let ini = null, fim = null;
    try { ini = seg(ev && ev.start); fim = seg(ev && ev.end); } catch (_) {}
    let s = sujo[rot];
    if (!s) s = sujo[rot] = { primeiro: agora, ultimo: agora, ini: ini, fim: fim, n: 0, info: false };
    else {
      s.ultimo = agora;
      if (ini === null || s.ini === null) s.ini = null; else s.ini = Math.min(s.ini, ini);
      if (fim === null || s.fim === null) s.fim = null; else s.fim = Math.max(s.fim, fim);
    }
    s.n++;
    if (info) s.info = true;
    ultimoAvisoFaixa = agora;
    avisosFaixa.push(agora);
    if (avisosFaixa.length > 50) avisosFaixa.shift();
    if (!fotoAcordada) fotoAcordada = agora;
    if (!info) muteSujo[rot] = agora;
  };
}

/* ------------------------------------------------------------ leitura do Premiere */
async function lerContexto() {
  const proj = await ppro.Project.getActiveProject();
  if (!proj) return null;
  const c = { proj: proj, projNome: proj.name || "", projCaminho: proj.path || "" };
  const seq = await proj.getActiveSequence();
  if (!seq) return c;
  c.seq = seq;
  c.seqId = String(seq.guid && seq.guid.toString ? seq.guid.toString() : seq.guid);
  c.nome = seq.name || "";
  return c;
}

async function idDe(pi) {
  try { const id = await aw(pi.getId()); return id === null || id === undefined ? null : str(id); } catch (_) { return null; }
}

async function caminhoDe(pi) {
  if (!pi) return null;
  const id = await idDe(pi);
  if (id && caminhos[id] !== undefined) return caminhos[id];
  let c = null;
  try {
    const clip = await aw(ppro.ClipProjectItem.cast(pi));
    if (clip) c = await clip.getMediaFilePath();
  } catch (_) { c = null; }     // sequencia aninhada / grafico: sem arquivo
  if (id) caminhos[id] = c || null;
  return c || null;
}

/* os getters de um item em paralelo (mesmos em video e audio). Velocidade (item 3) entra aqui:
 * cada um em tentar() - se getSpeed nao existir, o clipe continua sendo lido como no 0.1 */
async function lerCampos(it) {
  const ps = [it.getName(), it.getStartTime(), it.getEndTime(), it.getInPoint(), it.getOutPoint(),
              it.isDisabled(), it.getProjectItem()];
  if (MARCAS.vel !== false) {
    ps.push(tentar(function () { return it.getSpeed(); }));
    ps.push(tentar(function () { return it.isSpeedReversed(); }));
  }
  const v = await Promise.all(ps);
  let vel = null;
  if (MARCAS.vel !== false && v[7]) {
    if (v[7].e !== undefined) { falhou("vel", 20); naoDisponivel("velocidade (getSpeed)", v[7].e); }
    else if (typeof v[7].v === "number" && !isNaN(v[7].v)) {
      if (!MARCAS.vel) { MARCAS.vel = true; leituraOk("velocidade"); }
      /* a doc nao diz a unidade: acima de 20 = veio em % (100 = normal) e vira fator (SONDA passo 8). O sinal sai
       * SO do reverso: se o getSpeed ja vier negativo, o "* -1" desviraria (REVISAO-api 7) */
      let fator = Math.abs(v[7].v);
      if (fator > 20) fator = fator / 100;
      const reverso = !!(v[8] && v[8].v) || v[7].v < 0;
      vel = r4(fator * (reverso ? -1 : 1));
    }
  }
  const pi = v[6];
  const pid = pi ? await idDe(pi) : null;
  const caminho = await caminhoDe(pi);
  if (pid && pi) {
    let nomePi = "";
    try { nomePi = pi.name || ""; } catch (_) {}
    const m = mestres[pid];
    if (m) { m.pi = pi; m.caminho = caminho; if (nomePi) m.nome = nomePi; }
    else mestres[pid] = { pi: pi, nome: nomePi || v[0] || "", caminho: caminho };
  }
  return {
    nome: v[0] || "", inicio: r3(seg(v[1])), fim: r3(seg(v[2])), in: r3(seg(v[3])), out: r3(seg(v[4])),
    desligado: !!v[5], caminho: caminho, vel: vel, pid: pid
  };
}

function registro(tipo, i, c) {
  return { faixa: tipo + (i + 1), tipo: tipo, nome: c.nome, inicio: c.inicio, fim: c.fim, in: c.in, out: c.out,
           caminho: c.caminho, desligado: c.desligado, vel: c.vel };
}

/* a API nao tem id de clipe: identidade por geometria (o cache anda junto quando a foto casa um par) */
function chaveClipe(x) { return [x.faixa, x.inicio, x.in, x.caminho || x.nome].join("|"); }

async function lerTransicao(t, faixa) {
  const v = await Promise.all([tentar(function () { return t.getStartTime(); }), tentar(function () { return t.getEndTime(); }),
                               tentar(function () { return t.getName(); }), tentar(function () { return t.getMatchName(); })]);
  const r = { faixa: faixa, inicio: v[0].v ? r3(seg(v[0].v)) : null, fim: v[1].v ? r3(seg(v[1].v)) : null,
              nome: consertar(v[2].v || ""), match: v[3].v || "" };
  if (r.inicio === null && r.fim === null) r.so_contagem = true;     // plano B: getters nao responderam
  return r;
}

/* FOTO AMPLIADA: clipes (+vel) + faixas (nome, mute, assinatura) + transicoes + entrada/saida + legendas */
async function lerFoto(seq, prev) {
  const r = { itens: [], faixas: { V: [], A: [], L: [] }, trans: [], io: null, usos: {}, objs: {}, trs: { V: [], A: [] } };
  const nv = await seq.getVideoTrackCount();
  const na = await seq.getAudioTrackCount();
  const grupos = [["V", nv], ["A", na]];
  for (let g = 0; g < grupos.length; g++) {
    const tipo = grupos[g][0], n = grupos[g][1];
    for (let i = 0; i < n; i++) {
      let tr, itens;
      const info = { nome: "", mudo: null, sig: [] };
      r.faixas[tipo].push(info);
      r.trs[tipo].push(null);
      try { tr = tipo === "V" ? await seq.getVideoTrack(i) : await seq.getAudioTrack(i); } catch (_) { continue; }
      if (!tr) continue;
      r.trs[tipo][i] = tr;
      try { info.nome = tr.name || ""; } catch (_) {}
      if (MARCAS.mute !== false) {
        try { info.mudo = !!(await tr.isMuted()); if (!MARCAS.mute) { MARCAS.mute = true; leituraOk("mute"); } }
        catch (e) { falhou("mute", 3); naoDisponivel("mute da faixa (isMuted)", e); }
      }
      try { itens = (await aw(tr.getTrackItems(tipoClipe(), false))) || []; } catch (_) { continue; }
      for (let k = 0; k < itens.length; k++) {
        try {
          const c = await lerCampos(itens[k]);
          const rec = registro(tipo, i, c);
          r.itens.push(rec);
          info.sig.push(rec.inicio + "|" + rec.fim + "|" + (rec.caminho || rec.nome));
          r.objs[chaveClipe(rec)] = { it: itens[k], k: k };
          if (c.pid) (r.usos[c.pid] = r.usos[c.pid] || []).push(rec);
        } catch (_) { /* item estranho: pula */ }
      }
      if (MARCAS.trans !== false) {
        try {
          const ts = (await aw(tr.getTrackItems(tipoTransicao(), false))) || [];
          if (!MARCAS.trans) { MARCAS.trans = true; leituraOk("transicoes"); }
          for (let k = 0; k < ts.length; k++) {
            try { r.trans.push(await lerTransicao(ts[k], tipo + (i + 1))); } catch (_) {}
          }
        } catch (e) { falhou("trans", 3); naoDisponivel("transições (getTrackItems TRANSITION)", e); }
      }
    }
  }
  if (MARCAS.legendas !== false) {
    /* REVISAO-api 5 + desempenho 9: os tipos (26.3 / 26.5.1 / 27 beta) dizem que CaptionTrack.getTrackItems
     * devolve [] e a Adobe disse que item de legenda nao esta no UXP. So conta "ok" depois de ver alguma legenda;
     * e a faixa inteira so e relida a cada 10 s (nas outras fotos repete a contagem anterior) */
    try {
      const nl = await seq.getCaptionTrackCount();
      const prevL = (prev && prev.faixas && prev.faixas.L) || null;
      const recontar = Date.now() - ultimaContLeg >= T_LEGENDAS || !prevL || prevL.length !== nl;
      for (let j = 0; j < nl; j++) {
        const info = { nome: "", n: null };
        if (!recontar && prevL[j]) { info.nome = prevL[j].nome; info.n = prevL[j].n; r.faixas.L.push(info); continue; }
        try {
          const ct = await seq.getCaptionTrack(j);
          try { info.nome = ct.name || ""; } catch (_) {}
          info.n = ((await aw(ct.getTrackItems(tipoClipe(), false))) || []).length;
        } catch (_) {}
        r.faixas.L.push(info);
      }
      if (recontar) ultimaContLeg = Date.now();
      if (r.faixas.L.some(function (x) { return x.n > 0; })) {
        if (!MARCAS.legendas) { MARCAS.legendas = true; CAPAC.leituras["legendas (contagem)"] = "ok"; }
      } else if (!MARCAS.legendas && nl > 0) CAPAC.leituras["legendas (contagem)"] = "ok, mas sempre 0 (não confirmada)";
    } catch (e) { falhou("legendas", 3); naoDisponivel("faixas de legenda", e); }
  }
  if (MARCAS.io !== false) {
    try {
      /* sem nada marcado vem -400000 (SONDA 14/10) -> null = "nao marcado". O fim da sequencia vem junto (contexto) */
      const io = await Promise.all([seq.getInPoint(), seq.getOutPoint(), tentar(function () { return seq.getEndTime(); })]);
      r.io = { in: tempoMarcado(io[0]), out: tempoMarcado(io[1]), fim: io[2].v ? r3(seg(io[2].v)) : null };
      if (!MARCAS.io) { MARCAS.io = true; leituraOk("entrada/saida da sequencia"); }
    } catch (e) { falhou("io", 3); naoDisponivel("entrada/saída da sequência", e); }
  }
  return r;
}

async function tipoDoItem(it) {
  try {
    if (ppro.AudioClipTrackItem && it instanceof ppro.AudioClipTrackItem) return "A";
    if (ppro.VideoClipTrackItem && it instanceof ppro.VideoClipTrackItem) return "V";
  } catch (_) {}
  try {
    const g = await it.getMediaType();
    const s = String(g && g.toString ? g.toString() : g).toLowerCase();
    return s === AUDIO_GUID ? "A" : "V";
  } catch (_) { return "V"; }
}

async function lerItemSelecionado(it) {
  const tipo = await tipoDoItem(it);
  const c = await lerCampos(it);
  let faixa = null;
  try {
    const idx = await it.getTrackIndex();
    if (typeof idx === "number" && idx >= 0) faixa = tipo + (idx + 1);
  } catch (_) {}
  const est = atual && estadoSeq[atual.seqId];
  if (!faixa && est) {
    /* sem getTrackIndex: acha na ultima foto pelo tipo + inicio/fim (como o faixaDoClipe do DUBX) */
    const f = est.itens;
    for (let i = 0; i < f.length; i++) {
      if (f[i].tipo === tipo && Math.abs(f[i].inicio - c.inicio) < 0.02 && Math.abs(f[i].fim - c.fim) < 0.02) { faixa = f[i].faixa; break; }
    }
  }
  const rec = { faixa: faixa || tipo + "?", tipo: tipo, nome: c.nome, inicio: c.inicio, fim: c.fim, in: c.in, out: c.out,
                caminho: c.caminho, desligado: c.desligado, vel: c.vel };
  return { rec: rec, pid: c.pid };
}

/* ------------------------------------------------------------ DIFERENCA entre fotos (pura) */
const TOL = 0.002;
function perto(a, b) { return a !== null && b !== null && a !== undefined && b !== undefined && Math.abs(a - b) <= TOL; }
function mesmaMidia(a, d) {
  if (a.caminho || d.caminho) return String(a.caminho || "").toLowerCase() === String(d.caminho || "").toLowerCase();
  return a.nome === d.nome;
}
function sobrepoe(a, d) { return a.inicio < d.fim && d.inicio < a.fim; }
function velTxt(x) { return x.vel === null || x.vel === undefined ? "" : String(x.vel); }
function chaveExata(x) { return [x.faixa, x.inicio, x.fim, x.in, x.out, x.caminho, x.nome, x.desligado ? 1 : 0, velTxt(x)].join("|"); }

/* Ordem dos pareamentos importa: in/out iguais (= mesmo pedaco do arquivo) primeiro, senao num
 * ripple de clipes do MESMO bruto o item seguinte e confundido com trim do anterior. */
/* in na MIDIA: a API devolve o in DIVIDIDO pela velocidade (SONDA 14/10: 5,467 a 100% -> 2,733 a 200%, mesmo clipe) */
function velFator(x) { let v = Math.abs(x.vel || 1) || 1; if (v > 20) v = v / 100; return v; }
function inMidia(x) { return x.in === null || x.in === undefined ? null : x.in * velFator(x); }
/* CONFERENCIA 14/10: o in chega arredondado em 3 casas DEPOIS de dividido; x velocidade o erro cresce junto
 * (a 400% passava dos 2 ms do TOL e o Ctrl+R virava "apagou + colocou"). Tolerancia proporcional a velocidade. */
function pertoMidia(a, d) {
  const x = inMidia(a), y = inMidia(d);
  return x !== null && y !== null && Math.abs(x - y) <= TOL * Math.max(1, velFator(a), velFator(d));
}
const PASSES = [
  function (a, d) { return a.faixa === d.faixa && mesmaMidia(a, d) && perto(a.in, d.in) && perto(a.out, d.out); },   // andou no tempo / liga-desliga
  /* velocidade (Ctrl+R / Velocidade e Duracao / ferramenta Alongar taxa R): in e out mudam junto com a velocidade; o
   * in x velocidade (= na midia) fica; o inicio fica (Ctrl+R, R puxando o fim) OU o fim fica (R puxando o comeco) */
  function (a, d) { return a.faixa === d.faixa && mesmaMidia(a, d) && (perto(a.inicio, d.inicio) || perto(a.fim, d.fim)) && (a.vel || 1) !== (d.vel || 1) && pertoMidia(a, d); },
  function (a, d) { return a.tipo === d.tipo && mesmaMidia(a, d) && perto(a.in, d.in) && perto(a.out, d.out); },     // trocou de faixa
  function (a, d) { return a.faixa === d.faixa && mesmaMidia(a, d) && perto(a.inicio, d.inicio) && perto(a.in, d.in); }, // trim do fim / razor
  function (a, d) { return a.faixa === d.faixa && mesmaMidia(a, d) && perto(a.fim, d.fim) && perto(a.out, d.out); },  // trim do inicio
  function (a, d) { return a.faixa === d.faixa && mesmaMidia(a, d) && perto(a.inicio, d.inicio); },                     // ripple no inicio / slip
  function (a, d) { return a.faixa === d.faixa && mesmaMidia(a, d) && perto(a.inicio - a.in, d.inicio - d.in) && sobrepoe(a, d); }, // trim dos dois lados
  /* v0.2: grafico/texto SEM arquivo renomeado a mao (SONDA 14/10: o nome NAO acompanha o texto digitado - fica "Grafico"): mesmo lugar = mesmo clipe */
  function (a, d) { return a.faixa === d.faixa && !a.caminho && !d.caminho && perto(a.inicio, d.inicio) && perto(a.fim, d.fim) && perto(a.in, d.in) && perto(a.out, d.out); }
];

function mudancasDe(a, d) {
  const m = [];
  if (!perto(a.inicio, d.inicio)) m.push("inicio_mudou");
  if (!perto(a.fim, d.fim)) m.push("fim_mudou");
  if (!perto(a.in, d.in)) m.push("in_mudou");
  if (!perto(a.out, d.out)) m.push("out_mudou");
  if (a.faixa !== d.faixa) m.push("faixa_mudou");
  if (!!a.desligado !== !!d.desligado) m.push("ligado_mudou");
  if (a.nome !== d.nome) m.push("nome_mudou");
  if (a.vel !== null && a.vel !== undefined && d.vel !== null && d.vel !== undefined && Math.abs(a.vel - d.vel) > 0.0005) m.push("vel_mudou");
  return m;
}

function diffFotos(antes, depois) {
  const mapa = {};
  for (let i = 0; i < antes.length; i++) {
    const k = chaveExata(antes[i]);
    (mapa[k] = mapa[k] || []).push(antes[i]);
  }
  let restoD = [];
  for (let i = 0; i < depois.length; i++) {
    const l = mapa[chaveExata(depois[i])];
    if (l && l.length) l.pop(); else restoD.push(depois[i]);
  }
  let restoA = [];
  Object.keys(mapa).forEach(function (k) { mapa[k].forEach(function (a) { restoA.push(a); }); });
  const pares = [];
  for (let p = 0; p < PASSES.length && restoA.length && restoD.length; p++) {
    const casa = PASSES[p];
    const sobraA = [];
    for (let i = 0; i < restoA.length; i++) {
      const a = restoA[i];
      let melhor = -1, dist = Infinity;
      for (let j = 0; j < restoD.length; j++) {
        if (!casa(a, restoD[j])) continue;
        const dd = Math.abs(restoD[j].inicio - a.inicio);
        if (dd < dist) { dist = dd; melhor = j; }
      }
      if (melhor < 0) { sobraA.push(a); continue; }
      const d = restoD.splice(melhor, 1)[0];
      const m = mudancasDe(a, d);
      if (m.length) pares.push({ mudancas: m, antes: a, depois: d });
    }
    restoA = sobraA;
  }
  return { pares: pares, adicionados: restoD, removidos: restoA };
}

function temDiff(d) { return d.pares.length + d.adicionados.length + d.removidos.length > 0; }

/* Faixa nova NO MEIO renumera as de cima (V2 vira V3). Sem isto o diff acharia "moveu de faixa"
 * em todos os clipes de cima. Casa faixa velha com faixa nova pelo CONTEUDO (lista de clipes)
 * por alinhamento (programacao dinamica). Empate: a faixa nova fica em cima. Pura. */
function renumerarFaixas(sigsA, sigsD) {
  const nA = sigsA.length, nD = sigsD.length;
  function sim(a, d) {
    if (!a.length && !d.length) return 0.6;
    const s = {}, u = {};
    a.forEach(function (x) { s[x] = 1; u[x] = 1; });
    let inter = 0;
    d.forEach(function (x) { if (s[x] === 1) { inter++; s[x] = 2; } u[x] = 1; });
    return inter / Math.max(1, Object.keys(u).length);
  }
  const S = [];
  for (let i = 0; i <= nA; i++) { S.push([]); for (let j = 0; j <= nD; j++) S[i].push(0); }
  for (let i = 1; i <= nA; i++) {
    for (let j = 1; j <= nD; j++) {
      S[i][j] = Math.max(S[i - 1][j], S[i][j - 1], S[i - 1][j - 1] + 1 + sim(sigsA[i - 1], sigsD[j - 1]));
    }
  }
  const mapa = {};
  let i = nA, j = nD;
  while (i > 0 && j > 0) {
    const diag = S[i - 1][j - 1] + 1 + sim(sigsA[i - 1], sigsD[j - 1]);
    if (nD > nA && Math.abs(S[i][j] - S[i][j - 1]) < 1e-9) { j--; continue; }        // faixa nova (em cima, no empate)
    if (Math.abs(S[i][j] - diag) < 1e-9) { mapa[i - 1] = j - 1; i--; j--; continue; }
    if (Math.abs(S[i][j] - S[i - 1][j]) < 1e-9) { mapa[i - 1] = null; i--; continue; }
    j--;
  }
  while (i > 0) { mapa[i - 1] = null; i--; }
  const usadas = {};
  Object.keys(mapa).forEach(function (k) { if (mapa[k] !== null) usadas[mapa[k]] = true; });
  const novas = [], apagadas = [];
  for (let x = 0; x < nD; x++) if (!usadas[x]) novas.push(x);
  for (let x = 0; x < nA; x++) if (mapa[x] === null || mapa[x] === undefined) { mapa[x] = null; apagadas.push(x); }
  return { mapa: mapa, novas: novas, apagadas: apagadas };
}

/* transicoes: chave faixa|inicio|fim|nome. Pura. */
function diffTransicoes(antes, depois) {
  const out = [];
  const contar = function (l) { const c = {}; l.forEach(function (t) { if (t.so_contagem) c[t.faixa] = (c[t.faixa] || 0) + 1; }); return c; };
  const ca = contar(antes), cd = contar(depois);
  Object.keys(Object.assign({}, ca, cd)).forEach(function (f) {
    if ((ca[f] || 0) !== (cd[f] || 0)) out.push({ mudanca: "contagem", faixa: f, antes: ca[f] || 0, depois: cd[f] || 0 });
  });
  const A = antes.filter(function (t) { return !t.so_contagem; });
  const D = depois.filter(function (t) { return !t.so_contagem; });
  const k = function (t) { return [t.faixa, t.inicio, t.fim, t.nome].join("|"); };
  const mapa = {};
  A.forEach(function (t) { (mapa[k(t)] = mapa[k(t)] || []).push(t); });
  const restoD = [];
  D.forEach(function (t) { const l = mapa[k(t)]; if (l && l.length) l.pop(); else restoD.push(t); });
  const restoA = [];
  Object.keys(mapa).forEach(function (x) { mapa[x].forEach(function (t) { restoA.push(t); }); });
  const sobraA = [];
  restoA.forEach(function (a) {
    let melhor = -1;
    for (let j = 0; j < restoD.length; j++) {
      const d = restoD[j];
      if (d.faixa === a.faixa && d.inicio < a.fim + 0.05 && a.inicio < d.fim + 0.05) { melhor = j; break; }
    }
    if (melhor < 0) { sobraA.push(a); return; }
    const d = restoD.splice(melhor, 1)[0];
    out.push({ mudanca: d.nome !== a.nome ? "trocou" : "duracao", antes: a, depois: d });
  });
  sobraA.forEach(function (a) { out.push({ mudanca: "tirou", antes: a, depois: null }); });
  restoD.forEach(function (d) { out.push({ mudanca: "colocou", antes: null, depois: d }); });
  return out;
}

/* entre quais clipes a transicao esta (clipe que termina, clipe que comeca) */
function entreDe(t, itens) {
  if (!t || t.inicio === null || t.fim === null) return null;
  let a = null, b = null;
  for (let i = 0; i < itens.length; i++) {
    const x = itens[i];
    if (x.faixa !== t.faixa) continue;
    if (x.fim >= t.inicio - 0.01 && x.fim <= t.fim + 0.01 && x.inicio < t.inicio) a = x.nome;
    if (x.inicio >= t.inicio - 0.01 && x.inicio <= t.fim + 0.01 && x.fim > t.fim) b = x.nome;
  }
  return [a, b];
}

function assinaturaFoto(itens, trans) {
  const ks = itens.map(chaveExata).sort();
  const ts = (trans || []).map(function (t) { return [t.faixa, t.inicio, t.fim, t.nome].join("|"); }).sort();
  return hash(ks.join("\n") + "#" + ts.join("\n"));
}

function nomePadrao(n) { return /^\s*(v[ií]deo|video|[áa]udio|audio|legenda|legendas|caption|captions|subtitle|v|a|l)\s*\d+\s*$/i.test(String(n || "")); }

/* compara a foto anterior com a nova (renumera faixas antes). Pura: devolve o que mudou. */
function compararFotos(prev, f) {
  const out = { renum: {}, faixas: [], clipes: null, trans: [], io: null };
  let itensA = prev.itens, transA = prev.trans || [];
  const faixasA = { V: (prev.faixas.V || []).slice(), A: (prev.faixas.A || []).slice() };
  ["V", "A"].forEach(function (tipo) {
    const fa = prev.faixas[tipo] || [], fd = f.faixas[tipo] || [];
    if (fa.length === fd.length) return;
    const r = renumerarFaixas(fa.map(function (x) { return x.sig || []; }), fd.map(function (x) { return x.sig || []; }));
    const troca = {};
    const renumeradas = [];
    Object.keys(r.mapa).forEach(function (iA) {
      const iD = r.mapa[iA];
      if (iD === null) return;
      troca[tipo + (Number(iA) + 1)] = tipo + (iD + 1);
      if (Number(iA) !== iD) renumeradas.push(tipo + (Number(iA) + 1) + "->" + tipo + (iD + 1));
    });
    out.renum[tipo] = troca;
    const total = { V: (f.faixas.V || []).length, A: (f.faixas.A || []).length, L: (f.faixas.L || []).length };
    r.novas.forEach(function (iD) { out.faixas.push({ mudanca: "nova", faixa: tipo + (iD + 1), total: total, renumeradas: renumeradas }); });
    r.apagadas.forEach(function (iA) { out.faixas.push({ mudanca: "apagada", faixa: tipo + (iA + 1), total: total, renumeradas: renumeradas }); });
    const novaLista = [];
    for (let i = 0; i < fd.length; i++) novaLista.push(null);
    Object.keys(r.mapa).forEach(function (iA) { if (r.mapa[iA] !== null) novaLista[r.mapa[iA]] = fa[iA]; });
    faixasA[tipo] = novaLista;
  });
  const reTroca = function (x) {
    const t = out.renum[x.faixa ? x.faixa.charAt(0) : ""];
    if (!t || !t[x.faixa]) return x;
    return Object.assign({}, x, { faixa: t[x.faixa] });
  };
  if (Object.keys(out.renum).length) { itensA = itensA.map(reTroca); transA = transA.map(reTroca); }
  out.clipes = diffFotos(itensA, f.itens);
  out.trans = diffTransicoes(transA, f.trans || []);
  ["V", "A"].forEach(function (tipo) {
    const fa = faixasA[tipo] || [], fd = f.faixas[tipo] || [];
    for (let i = 0; i < fd.length; i++) {
      const a = fa[i], d = fd[i];
      if (!a || !d) continue;
      if (a.mudo !== null && d.mudo !== null && a.mudo !== undefined && d.mudo !== undefined && a.mudo !== d.mudo)
        out.faixas.push({ mudanca: "mute", faixa: tipo + (i + 1), antes: a.mudo, depois: d.mudo });
      /* nome padrao ("Video 2") acompanha o numero da faixa: so conta nome dado por ele */
      if ((a.nome || "") !== (d.nome || "") && !(nomePadrao(a.nome) && nomePadrao(d.nome)))
        out.faixas.push({ mudanca: "renomeou", faixa: tipo + (i + 1), antes: a.nome, depois: d.nome });
    }
  });
  const la = prev.faixas.L || [], ld = f.faixas.L || [];
  if (la.length !== ld.length) {
    const total = { V: (f.faixas.V || []).length, A: (f.faixas.A || []).length, L: ld.length };
    if (ld.length > la.length) for (let i = la.length; i < ld.length; i++) out.faixas.push({ mudanca: "nova", faixa: "L" + (i + 1), total: total, renumeradas: [] });
    else for (let i = ld.length; i < la.length; i++) out.faixas.push({ mudanca: "apagada", faixa: "L" + (i + 1), total: total, renumeradas: [] });
  }
  if (prev.io && f.io) {
    /* null = nao marcado (SONDA 14/10: -400000 vira null em tempoMarcado). null -> null nao e mudanca */
    const igualIO = function (a, b) { return (a === null || a === undefined) ? (b === null || b === undefined) : perto(a, b); };
    const saidaNoFim = function (x) { return x.fim !== null && x.fim !== undefined && x.out !== null && x.out !== undefined && Math.abs(x.out - x.fim) <= 0.05; };
    const mudouIn = !igualIO(prev.io.in, f.io.in);
    const mudouOut = !igualIO(prev.io.out, f.io.out) && !(saidaNoFim(prev.io) && saidaNoFim(f.io));     // (protecao antiga, inofensiva)
    if (mudouIn || mudouOut) out.io = { antes: prev.io, depois: f.io };
  }
  return out;
}

/* pontos onde o snap gruda: bordas dos clipes que NAO mudaram nesta foto, agulha e marcadores da sequencia.
 * Uma volta "exata" que cai so em ponto de snap pode ter sido a mao (REVISAO-resumo 1) */
function pontosDeSnap(f, d) {
  const mudou = {};
  d.pares.forEach(function (p) { mudou[chaveExata(p.depois)] = 1; });
  d.adicionados.forEach(function (x) { mudou[chaveExata(x)] = 1; });
  const pts = {};
  const por = function (t) { if (t !== null && t !== undefined && !isNaN(t)) pts[Math.round(t * 1000)] = 1; };
  f.itens.forEach(function (x) { if (!mudou[chaveExata(x)]) { por(x.inicio); por(x.fim); } });
  if (ag) por(ag.pos);
  const mk = atual && marcasSeq[atual.seqId];
  if (mk) Object.keys(mk.mapa).forEach(function (k) { por(mk.mapa[k].t); });
  return pts;
}
function caiuNoSnap(p, pts) {
  const bordas = [];
  if (p.mudancas.indexOf("inicio_mudou") >= 0) bordas.push(p.depois.inicio);
  if (p.mudancas.indexOf("fim_mudou") >= 0) bordas.push(p.depois.fim);
  if (!bordas.length) return false;
  /* arrastando um clipe, basta UMA borda grudar (a outra anda junto); no trim so muda uma borda */
  return bordas.some(function (t) {
    const k = Math.round(t * 1000);
    return !!(pts[k] || pts[k - 1] || pts[k + 1] || pts[k - 2] || pts[k + 2]);
  });
}

/* cache de efeitos anda com o clipe que andou e some com o clipe apagado (REVISAO-desempenho 7).
 * Em duas fases: num ripple um clipe pode ir pra chave que outro acabou de deixar. */
function moverCaches(pares, removidos) {
  const mov = {};
  pares.forEach(function (p) { const ka = chaveClipe(p.antes), kd = chaveClipe(p.depois); if (ka !== kd) mov[ka] = kd; });
  const apagar = {};
  removidos.forEach(function (x) { apagar[chaveClipe(x)] = 1; });
  if (!Object.keys(mov).length && !Object.keys(apagar).length) return;
  const novo = { c: {}, l: {}, f: {}, t: {}, h: {} };
  const tirar = function (ka, kd) {
    if (efCache[ka]) { if (kd) novo.c[kd] = efCache[ka]; delete efCache[ka]; }
    if (efLista[ka]) { if (kd) novo.l[kd] = efLista[ka]; delete efLista[ka]; }
    if (efLista[ka + "#fundo"]) { if (kd) novo.f[kd] = efLista[ka + "#fundo"]; delete efLista[ka + "#fundo"]; }
    if (ehTexto[ka]) { if (kd) novo.t[kd] = true; delete ehTexto[ka]; }
  };
  Object.keys(apagar).forEach(function (k) { tirar(k, null); });
  Object.keys(mov).forEach(function (ka) { tirar(ka, mov[ka]); });
  /* efHist: chave = chaveClipe + "|" + match + "|" + idx */
  Object.keys(efHist).forEach(function (h) {
    const i2 = h.lastIndexOf("|"), i1 = h.lastIndexOf("|", i2 - 1);
    const kc = h.slice(0, i1);
    if (apagar[kc]) { delete efHist[h]; return; }
    if (mov[kc]) { novo.h[mov[kc] + h.slice(i1)] = efHist[h]; delete efHist[h]; }
  });
  Object.keys(novo.c).forEach(function (k) { efCache[k] = novo.c[k]; });
  Object.keys(novo.l).forEach(function (k) { efLista[k] = novo.l[k]; });
  Object.keys(novo.f).forEach(function (k) { efLista[k + "#fundo"] = novo.f[k]; });
  Object.keys(novo.t).forEach(function (k) { ehTexto[k] = true; });
  Object.keys(novo.h).forEach(function (k) { efHist[k] = novo.h[k]; });
}

function temAlgo(c) { return temDiff(c.clipes) || c.trans.length > 0 || c.faixas.length > 0 || !!c.io; }

/* ------------------------------------------------------------ capturas: agulha */
async function passoAgulha() {
  const c = await lerContexto();
  if (!c || !c.seq) { atual = null; return; }
  if (!atual || atual.seqId !== c.seqId) {
    /* objetos do Premiere da sequencia anterior nao ficam presos (o diff so precisa de itens/faixas/trans) */
    if (atual && estadoSeq[atual.seqId]) { estadoSeq[atual.seqId].objs = {}; estadoSeq[atual.seqId].trs = { V: [], A: [] }; }
    atual = c;
    ag = null; velAnt = null;
    let zero = null;
    try { zero = r3(seg(await c.seq.getZeroPoint())); } catch (_) {}
    empurrar({ tipo: "sequencia", seq_id: c.seqId, nome: c.nome, projeto: c.projNome, zero: zero });
    selSig = null;
    selBarata = null;
    selSuja = Date.now();
  } else {
    atual.seq = c.seq;
    atual.nome = c.nome;
    atual.proj = c.proj;
  }
  const pos = seg(await c.seq.getPlayerPosition());
  const ms = Date.now();
  if (pos === null) return;
  let vel = 0, de = null;
  if (ag) {
    const dt = (ms - ag.ms) / 1000;
    de = ag.pos;
    if (dt > 0) vel = (pos - ag.pos) / dt;
  }
  /* "tocando" e deduzido (a API nao tem isPlaying). v0.2: so com velocidade ESTAVEL entre duas
   * amostras seguidas (defeito B: arrastar a agulha dava 1,9 / 2,3 / 6,3 / 0,7 e virava "play") */
  const passoCurto = ag && (ms - ag.ms) < 600;
  const naFaixa = !!(passoCurto && Math.abs(vel) >= 0.5 && Math.abs(vel) <= 8.5);
  const tocando = naFaixa && velAnt !== null && Math.abs(vel - velAnt) <= 0.35 * Math.abs(vel);
  velAnt = naFaixa ? vel : null;
  tocandoAgora = tocando;
  const mudou = !agEmitida || agEmitida.seqId !== c.seqId || Math.abs(pos - agEmitida.pos) > 0.0005;
  if (mudou || retomadaPendente) {
    const ev = { tipo: "agulha", seq_id: c.seqId, pos: r3(pos), de: de === null ? null : r3(de),
                 vel: Math.round(vel * 100) / 100, tocando: tocando, ms: ms };
    if (retomadaPendente) { ev.retomada = true; retomadaPendente = false; }
    empurrar(ev);
    agEmitida = { pos: pos, seqId: c.seqId };
  }
  ag = { pos: pos, ms: ms };
}

/* ------------------------------------------------------------ selecao */
async function passoSelecao() {
  if (!atual) return;
  const a = atual;
  const sel = await a.seq.getSelection();
  let itens = sel ? await aw(sel.getTrackItems()) : [];
  itens = itens || [];
  /* assinatura barata (3 chamadas por item) antes da leitura completa (~11): sem mudanca, para aqui */
  const baratas = await Promise.all(itens.slice(0, MAX_SEL).map(async function (it) {
    try {
      const v = await Promise.all([it.getStartTime(), it.getEndTime(), it.getTrackIndex()]);
      return [r3(seg(v[0])), r3(seg(v[1])), v[2]].join(",");
    } catch (_) { return "?"; }
  }));
  const barata = itens.length + "#" + baratas.join("|");
  if (barata === selBarata) return;
  const lidos = [], objs = [], pids = [];
  for (let i = 0; i < itens.length && i < MAX_SEL; i++) {
    try {
      const r = await lerItemSelecionado(itens[i]);
      lidos.push(r.rec);
      if (objs.length < 4) objs.push({ it: itens[i], rec: r.rec });
      if (r.pid && pids.indexOf(r.pid) < 0 && pids.length < 8) pids.push(r.pid);
    } catch (_) {}
  }
  if (!atual || atual.seqId !== a.seqId) return;
  lidos.sort(function (x, y) { return (x.tipo === y.tipo ? 0 : (x.tipo === "V" ? -1 : 1)) || (x.faixa < y.faixa ? -1 : x.faixa > y.faixa ? 1 : 0) || (x.inicio - y.inicio); });
  const sig = JSON.stringify(lidos) + "#" + itens.length;
  selBarata = barata;
  selObjs = objs;
  selMestres = pids;
  if (sig !== selSig) {
    if (selSig !== null || lidos.length) empurrar({ tipo: "selecao", seq_id: a.seqId, itens: lidos, total: itens.length });
    selSig = sig;
    ultimaFundaSel = 0;          // selecionou outro clipe: leitura funda (base) logo
  }
}

async function passoSelecaoTick() {
  const agora = Date.now();
  if (agora - selInicio < T_SEL_MIN) return false;
  /* so relaxa pra 1 s depois que o aviso CHEGOU de verdade (ligar quase nunca falha; o aviso pode nao existir
   * no 26.5.2): antes disso, 250 ms como o 0.1 (REVISAO-api 2) */
  const comAviso = (CAPAC.disparos.selecao_mudou || 0) > 0;
  let vez;
  if (selSuja && selSuja >= selInicio) {
    /* arrasto de selecao = rajada de avisos: le 150 ms depois do ULTIMO (ou 600 ms depois do 1o) */
    vez = agora - selSuja >= SEL_SILENCIO || (selSujaPrimeiro > 0 && agora - selSujaPrimeiro >= 600);
  } else vez = agora - selInicio >= (comAviso ? T_SEL_REDE : T_SEL_SEM_AVISO);
  if (!vez) return false;
  selInicio = agora;
  selSuja = 0;
  selSujaPrimeiro = 0;
  await passoSelecao();
  return true;
}

/* ------------------------------------------------------------ marcadores (item 1) */
function promessa(x) { return !!(x && typeof x.then === "function"); }
async function lerMarcadoresDe(dono) {
  const mk = await ppro.Markers.getMarkers(dono);
  const arr = (mk ? await aw(mk.getMarkers()) : []) || [];
  const mapa = {};
  for (let i = 0; i < arr.length; i++) {
    const m = arr[i];
    try {
      /* os get* do Marker sao SINCRONOS (.d.ts 26.5.1): sem await (cada await e uma pausa a toa por marcador).
       * Se um dia vierem Promise, espera todos juntos. */
      let v = [m.getStart(), m.getName(), m.getDuration(), m.getColorIndex(), m.getComments()];
      if (v.some(promessa)) v = await Promise.all(v);
      const t = r3(seg(v[0]));
      const nome = v[1];
      let id = null;
      try { id = m.guid && m.guid.toString ? m.guid.toString() : null; } catch (_) {}
      id = id || ("t" + t + "_" + nome);
      mapa[id] = { id: id, nome: nome || "", t: t, dur: r3(seg(v[2])), cor: v[3], coment: v[4] || "" };
    } catch (_) {}
  }
  return mapa;
}

/* diferenca de marcadores (pura). Defeito E: marcador SEM guid ganha id pelo tempo; se ele
 * andou, casa "sumiu + apareceu" de mesmo nome/cor pelo mais perto = "mudou" */
function diffMarcadores(ant, mapa) {
  const out = [];
  const novos = [], sumidos = [];
  Object.keys(mapa).forEach(function (id) {
    const d = mapa[id], x = ant[id];
    if (!x) novos.push(d);
    else if (x.nome !== d.nome || !perto(x.t, d.t) || !perto(x.dur, d.dur) || x.coment !== d.coment || x.cor !== d.cor)
      out.push({ mudanca: "mudou", antes: x, depois: d });
  });
  Object.keys(ant).forEach(function (id) { if (!mapa[id]) sumidos.push(ant[id]); });
  const sobraN = [];
  novos.forEach(function (d) {
    let melhor = -1, dist = Infinity;
    if (String(d.id).charAt(0) === "t") {
      for (let i = 0; i < sumidos.length; i++) {
        const x = sumidos[i];
        if (String(x.id).charAt(0) !== "t" || x.nome !== d.nome || x.cor !== d.cor) continue;
        const dd = Math.abs((x.t || 0) - (d.t || 0));
        if (dd < dist) { dist = dd; melhor = i; }
      }
    }
    if (melhor >= 0) out.push({ mudanca: "mudou", antes: sumidos.splice(melhor, 1)[0], depois: d });
    else sobraN.push(d);
  });
  sobraN.forEach(function (d) { out.push({ mudanca: "novo", antes: null, depois: d }); });
  sumidos.forEach(function (x) { out.push({ mudanca: "removido", antes: x, depois: null }); });
  return out;
}

/* ritmo de leitura de marcadores por dono: 0,5 s (marcar no beat), mas no maximo 25% do tempo daquele dono */
const ritmoMarc = {};          // dono -> {proxima, ms}
function vezDoDono(dono) { const r = ritmoMarc[dono]; return !r || Date.now() >= r.proxima; }
function marcarRitmo(dono, gasto) { ritmoMarc[dono] = { proxima: Date.now() + Math.min(5000, Math.max(T_MARCADORES, 4 * gasto)) - T_MARCADORES / 2, ms: gasto }; }

async function lerMarcadoresSeq(a) {
  let mapa;
  if (!vezDoDono("seq:" + a.seqId)) return;
  const t0 = Date.now();
  try { mapa = await lerMarcadoresDe(a.seq); marcarRitmo("seq:" + a.seqId, Date.now() - t0); }
  catch (e) { logar("aviso", "marcadores: " + msgErro(e)); return; }
  const agora = Date.now();
  const ant = marcasSeq[a.seqId];
  if (ant) {
    diffMarcadores(ant.mapa, mapa).forEach(function (m) {
      empurrar({ tipo: "marcador", alvo: "sequencia", seq_id: a.seqId, mudanca: m.mudanca, antes: m.antes, depois: m.depois,
                 janela_ms: [ant.ms, agora], ms: ant.ms + Math.min(agora - ant.ms, 250) });
    });
  }
  marcasSeq[a.seqId] = { mapa: mapa, ms: agora };
}

/* tempo do marcador do clipe-mestre -> timeline. Pura (testada no --unidade).
 *  - o tempo do marcador vem na MIDIA (SUPOSICAO: a SONDA de 14/10 nao separou, o clipe comecava em 0 com in 0);
 *  - MEDIDO na SONDA (passos 3 e 8, mesmo clipe): com velocidade, getInPoint/getOutPoint vem DIVIDIDOS pela
 *    velocidade (in 5,467 / out 21,033 a 100% -> 2,733 / 10,517 a 200%). Na midia: in x vel .. out x vel. */
function posNaTimeline(u, t) {
  if (t === null || t === undefined || u.in === null || u.out === null || u.in === undefined || u.out === undefined) return null;
  let v = Math.abs(u.vel || 1) || 1;
  if (v > 20) v = v / 100;           // velocidade em % (o lerCampos ja converte; aqui e so seguro)
  const lo = Math.min(u.in, u.out) * v, hi = Math.max(u.in, u.out) * v;
  const folga = 0.001 * Math.max(1, v);    // in/out chegam arredondados DEPOIS de divididos: o erro cresce com a velocidade
  if (t < lo - folga || t > hi + folga) return null;
  const pos = (u.vel !== null && u.vel !== undefined && u.vel < 0) ? u.inicio + (hi - t) / v : u.inicio + (t - lo) / v;
  return r3(pos);
}
function usosDe(pid, t) {
  const est = atual && estadoSeq[atual.seqId];
  const l = (est && est.usos[pid]) || [];
  const out = [];
  for (let i = 0; i < l.length; i++) {
    const pos = posNaTimeline(l[i], t);
    if (pos !== null) out.push({ faixa: l[i].faixa, nome: l[i].nome, pos: pos });
  }
  return out;
}

async function lerMarcadoresMestre(pid, origem) {
  if (MARCAS.marcClipe === false) return;
  const m = mestres[pid];
  if (!m || !m.pi) return;
  if (origem === "selecionado" && !vezDoDono(pid)) return;
  let mapa;
  const t0 = Date.now();
  try {
    const clip = await aw(ppro.ClipProjectItem.cast(m.pi));
    if (!clip) return;
    mapa = await lerMarcadoresDe(clip);
    marcarRitmo(pid, Date.now() - t0);
    if (!MARCAS.marcClipe) { MARCAS.marcClipe = true; leituraOk("marcadores de clipe"); }
  } catch (e) {
    m.falhas = (m.falhas || 0) + 1;
    if (m.falhas >= 3) delete mestres[pid];
    falhou("marcClipe", 5);
    naoDisponivel("marcadores de clipe (Markers.getMarkers(ClipProjectItem))", e);
    return;
  }
  const agora = Date.now();
  const ant = marcasClipe[pid];
  if (ant) {
    diffMarcadores(ant.mapa, mapa).forEach(function (x) {
      const mk = x.depois || x.antes;
      empurrar({ tipo: "marcador", alvo: "clipe", mudanca: x.mudanca, antes: x.antes, depois: x.depois,
                 mestre: { id: pid, nome: m.nome, caminho: m.caminho }, usos: usosDe(pid, mk ? mk.t : null),
                 origem: origem, janela_ms: [ant.ms, agora], ms: ant.ms + Math.min(agora - ant.ms, 250) });
    });
  }
  marcasClipe[pid] = { mapa: mapa, ms: agora };
}

async function passoMarcadores() {
  const a = atual;
  if (!a) return false;
  const agora = Date.now();
  const ant = marcasSeq[a.seqId];
  const grande = ant && Object.keys(ant.mapa).length > 200;
  if (!grande || agora - ultimaMarcSeq >= T_MARCADORES_SEQ_GRANDE) { ultimaMarcSeq = agora; await lerMarcadoresSeq(a); }
  /* REVISAO-desempenho 5: este laco roda TOCANDO e fora do orcamento geral. Tocando: so a sequencia + o 1o
   * clipe selecionado (a musica do M no beat). Parado: os selecionados em rodizio, no maximo ~40 ms por volta. */
  const pids = selMestres.slice(0, 8);
  if (!pids.length) return true;
  if (tocandoAgora) { await lerMarcadoresMestre(pids[0], "selecionado"); return true; }
  let lidos = 0;
  for (let n = 0; n < pids.length; n++) {
    if (n > 0 && Date.now() - agora > T_MARC_VOLTA_MAX) break;
    await lerMarcadoresMestre(pids[(rodizioSelMestre + n) % pids.length], "selecionado");
    lidos++;
  }
  rodizioSelMestre = (rodizioSelMestre + lidos) % pids.length;
  return true;
}

/* ------------------------------------------------------------ FOTO */
async function tirarFoto(acordadaEm) {
  const a = atual;
  if (!a || fotoRodando) return;
  fotoRodando = true;
  const t0 = Date.now();
  try {
    let f = await lerFoto(a.seq, estadoSeq[a.seqId]);
    if (!atual || atual.seqId !== a.seqId) return;      // trocou de sequencia no meio: descarta
    const prev = estadoSeq[a.seqId];
    const ms = Date.now() - t0;
    if (!prev) {
      empurrar({ tipo: "foto_inicial", seq_id: a.seqId, itens: f.itens, ms_leitura: ms, ms: t0,
                 faixas: { V: f.faixas.V.map(function (x) { return { nome: x.nome, mudo: x.mudo }; }),
                           A: f.faixas.A.map(function (x) { return { nome: x.nome, mudo: x.mudo }; }),
                           L: f.faixas.L.length },
                 transicoes: f.trans.length, entrada_saida: f.io });
      estadoSeq[a.seqId] = f;
      historico[a.seqId] = [{ h: assinaturaFoto(f.itens, f.trans), foto: 0, ms: t0 }];
    } else {
      let c = compararFotos(prev, f);
      if (temAlgo(c)) {
        /* releitura: uma foto lida DURANTE a edicao pode sair meio antes/meio depois */
        f = await lerFoto(a.seq, prev);
        if (!atual || atual.seqId !== a.seqId) return;
        c = compararFotos(prev, f);
      }
      if (temAlgo(c)) {
        fotoN++;
        /* hora do evento = o 1o aviso de faixa desde a ultima foto, nao a hora da leitura: com a musica tocando a
         * foto espera e o Ctrl+K no beat saia ate 10 s atrasado (REVISAO-resumo 4) */
        const msEv = (acordadaEm && acordadaEm < t0) ? acordadaEm : t0;
        const comum = { seq_id: a.seqId, carga: CARGA, foto: fotoN, ms: msEv, janela_ms: [fimUltimaFoto || t0, t0] };
        if (aposPausa) comum.apos_pausa = true;
        if (tocandoAgora) comum.tocando = true;
        c.faixas.forEach(function (x) { empurrar(Object.assign({}, comum, { tipo: "faixa" }, x)); });
        const tl = Object.assign({ tipo: "timeline" }, comum);
        const d = c.clipes;
        let snaps = null;
        try { if (d.pares.length) snaps = pontosDeSnap(f, d); } catch (_) {}
        d.pares.forEach(function (p) {
          const ev = Object.assign({}, tl, { mudancas: p.mudancas, antes: p.antes, depois: p.depois });
          try { if (snaps && caiuNoSnap(p, snaps)) ev.snap = true; } catch (_) {}
          empurrar(ev);
        });
        d.removidos.forEach(function (x) { empurrar(Object.assign({}, tl, { mudancas: ["removido"], antes: x, depois: null })); });
        d.adicionados.forEach(function (x) { empurrar(Object.assign({}, tl, { mudancas: ["adicionado"], antes: null, depois: x })); });
        /* ate aqui e o que o 0.1 ja fazia: o estado anda AGORA. Se um bloco novo abaixo der erro, as mesmas linhas
         * nao voltam a cada foto e o painel nao fica vermelho (REVISAO-api 10) */
        estadoSeq[a.seqId] = f;
        try {
        c.trans.forEach(function (t) {
          const ev = Object.assign({}, comum, { tipo: "transicao", mudanca: t.mudanca });
          if (t.mudanca === "contagem") { ev.faixa = t.faixa; ev.antes = t.antes; ev.depois = t.depois; }
          else {
            ev.antes = t.antes ? Object.assign({}, t.antes, { entre: entreDe(t.antes, prev.itens) }) : null;
            ev.depois = t.depois ? Object.assign({}, t.depois, { entre: entreDe(t.depois, f.itens) }) : null;
          }
          empurrar(ev);
        });
        } catch (e) { naoDisponivel("foto: transições", e); }
        try { if (c.io) empurrar(Object.assign({}, comum, { tipo: "entrada_saida", antes: c.io.antes, depois: c.io.depois })); }
        catch (e) { naoDisponivel("foto: entrada/saída", e); }
        /* texto (item 6): o paliativo "o nome do clipe acompanha o texto digitado" CAIU na SONDA (14/10, passo 7: escreveu
         * TESTE -> TESTE 2 e o clipe continuou "Grafico"; o "Texto de origem" volta null). Nome de grafico que muda = ele
         * RENOMEOU o clipe a mao: sai como a mudanca de nome normal da timeline, nao como "editou o texto". */
        /* desfazer provavel (camada 1): a timeline voltou EXATAMENTE a um estado ja fotografado */
        try {
        const h = assinaturaFoto(f.itens, f.trans);
        const hist = historico[a.seqId] || (historico[a.seqId] = []);
        if (hist.length && hist[hist.length - 1].h !== h) {
          for (let i = hist.length - 2; i >= 0; i--) {
            if (hist[i].h === h) {
              empurrar(Object.assign({}, comum, { tipo: "desfazer_provavel", alvo: "timeline", volta_a_foto: hist[i].foto, volta_a_ms: hist[i].ms,
                                                  desfaz_fotos: hist.slice(i + 1).map(function (x) { return x.foto; }) }));
              break;
            }
          }
        }
        hist.push({ h: h, foto: fotoN, ms: msEv });
        if (hist.length > 30) hist.shift();
        } catch (e) { naoDisponivel("foto: desfazer provável", e); }
        /* clipe que andou leva junto o que ja se sabe dos efeitos dele; clipe apagado larga o cache */
        try { moverCaches(d.pares, d.removidos); } catch (e) { naoDisponivel("foto: cache de efeitos", e); }
      }
      estadoSeq[a.seqId] = f;
    }
    aposPausa = false;
    try { ligarFaixas(a.seqId, f.trs); } catch (e) { naoDisponivel("ouvintes de faixa", e); }
    const total = Date.now() - t0;
    if (total > 1000 && !avisouLenta) {
      avisouLenta = true;
      logar("aviso", "foto da timeline lenta: " + (total / 1000).toFixed(1) + " s para " + f.itens.length +
            " itens (proxima foto so depois de " + (total * (OCUPACAO_FOTO - 1) / 1000).toFixed(1) + " s)");
    }
  } finally {
    fotoRodando = false;
    fimUltimaFoto = Date.now();
  }
}

/* a foto do laco (a final, de pausar/concluir, chama tirarFoto direto e nunca pula) */
async function passoFoto() {
  if (!atual || fotoRodando) return false;
  const agora = Date.now();
  const temBase = !!estadoSeq[atual.seqId];
  if (tocandoAgora && temBase && agora - fimUltimaFoto < T_FOTO_TOCANDO) {
    /* tocando: so a foto BARATA acordada por aviso de faixa (Ctrl+K / Q / W no beat), no maximo 1 a cada 2 s */
    if (!(fotoAcordada && ultimaFotoMs <= FOTO_BARATA_MS && agora - fimUltimaFoto >= 2000)) return false;
  }
  if (temBase) {
    const silencio = agora - ultimoAvisoFaixa >= SILENCIO_MS || (fotoAcordada && agora - fotoAcordada >= RAJADA_MAX_MS * 2);
    const acordada = fotoAcordada && silencio;
    if (agora < fotoProxima && !(acordada && agora >= fotoMinima)) return false;
    if (fotoAcordada && !silencio && agora < fotoProxima + 2000) return false;     // aviso chegando: espera o silencio
    /* a foto (o coracao do 0.1) obedece so a regra dela - 4x o proprio tempo -, nao o teto dos outros lacos
     * (REVISAO-api 9: com o teto, ela chegava a esperar 5 s e um trim + Ctrl+Z sumia) */
  }
  const acordadaEm = fotoAcordada;
  fotoAcordada = 0;
  const t0 = Date.now();
  await tirarFoto(acordadaEm);
  const gasto = Date.now() - t0;
  ultimaFotoMs = gasto;
  fotoProxima = Date.now() + Math.max(T_FOTO_MIN, gasto * OCUPACAO_FOTO) - gasto;
  fotoMinima = Date.now() + Math.max(T_FOTO_MIN_ACORDADA, gasto * OCUPACAO_FOTO) - gasto;
  return true;
}

/* ------------------------------------------------------------ efeitos (item 3) */
/* valor de parametro -> JSON curto (desembrulha como o GRADEX: kf.value.value -> kf.value -> kf) */
async function valorDe(x, fino) {
  let v = x;
  try {
    if (v && typeof v === "object" && v.value !== undefined && (v.position !== undefined || (v.value && v.value.value !== undefined)))
      v = (v.value && v.value.value !== undefined) ? v.value.value : v.value;
  } catch (_) {}
  if (v === null || v === undefined) return null;
  const t = typeof v;
  /* fino = VOLUME: vem em amplitude (SONDA 14/10: 0 dB = 0,177828; teto +15 dB = 1,0), 4 casas perdiam ~1 dB em volume
   * baixo -> 6 algarismos significativos. O resto continua com 4 casas (nao muda nada do que ja era comparado) */
  if (t === "number") return (fino && v !== 0 && Math.abs(v) < 1) ? Number(v.toPrecision(6)) : r4(v);
  if (t === "string" || t === "boolean") return v;
  try { if (ppro.MogrtText && v instanceof ppro.MogrtText) return { texto: String(await aw(v.getText())) }; } catch (_) {}
  try { if (v.red !== undefined) return [r4(v.red), r4(v.green), r4(v.blue), r4(v.alpha)]; } catch (_) {}
  try { if (v.x !== undefined && v.y !== undefined) return [r4(v.x), r4(v.y)]; } catch (_) {}
  try { const j = JSON.parse(JSON.stringify(v)); return (j && typeof j === "object" && !Object.keys(j).length) ? null : j; } catch (_) { return null; }
}

async function lerParametro(p, j, antP, reusarKf, fino) {
  const r = { idx: j, nome: "", v: null };
  try { r.nome = consertar(p.displayName || ""); } catch (_) {}
  try { r.v = await valorDe(await p.getStartValue(), fino); } catch (_) { r.v = null; }
  let tv = false;
  try { tv = !!(await aw(p.isTimeVarying())); } catch (_) {}
  if (tv) {
    try {
      const ks = (await aw(p.getKeyframeListAsTickTimes())) || [];
      r.nk = ks.length; r.kf = [];
      for (let k = 0; k < ks.length && k < 50; k++) r.kf.push(r3(seg(ks[k])));
      /* rede periodica (sem aviso) com os mesmos tempos de keyframe: reaproveita os valores (REVISAO-desempenho 4).
       * Leitura de AVISO le tudo: mexer no valor de um keyframe nao muda os tempos. */
      if (reusarKf && antP && antP.kf && antP.kv && igual(antP.kf, r.kf)) r.kv = antP.kv.slice();
      else {
        r.kv = [];
        for (let k = 0; k < r.kf.length; k++) {
          let v = null;
          try { v = await valorDe(await p.getValueAtTime(ks[k]), fino); } catch (_) {}    // da erro em tipo texto
          r.kv.push(v);
        }
      }
    } catch (_) {}
  }
  return r;
}

/* componente correspondente na leitura anterior (mesmo matchName; de preferencia na mesma posicao) */
function compAnterior(ant, comp, usados) {
  if (!ant) return null;
  if (ant[comp.idx] && ant[comp.idx].match === comp.match && !usados[comp.idx]) { usados[comp.idx] = 1; return ant[comp.idx]; }
  for (let i = 0; i < ant.length; i++) if (!usados[i] && ant[i].match === comp.match) { usados[i] = 1; return ant[i]; }
  return null;
}

/* leitura funda com teto de tempo (REVISAO-desempenho 4): passou de 150 ms, o resto dos parametros nao e lido
 * (os componentes seguintes so pelo nome) e a parte que faltou repete a leitura anterior - nao vira mudanca */
async function lerEfeitos(it, ant, reusarKf) {
  const t0 = Date.now();
  const cadeia = await it.getComponentChain();
  const n = await aw(cadeia.getComponentCount());
  const comps = [];
  const usados = {};
  let estourou = false;
  for (let i = 0; i < n; i++) {
    try {
      const c = await aw(cadeia.getComponentAtIndex(i));
      const nm = await Promise.all([tentar(function () { return c.getMatchName(); }), tentar(function () { return c.getDisplayName(); })]);
      const comp = { idx: i, match: nm[0].v ? String(nm[0].v) : "?", nome: consertar(nm[1].v || ""), params: [] };
      const antC = compAnterior(ant, comp, usados);
      if (!estourou) {
        const np = await aw(c.getParamCount());
        for (let j = 0; j < np && j < 200; j++) {
          if (Date.now() - t0 > T_FUNDA_MAX) { estourou = true; break; }
          try { comp.params.push(await lerParametro(await aw(c.getParam(j)), j, antC && antC.params[j], reusarKf, /volume/i.test(comp.match))); }
          catch (_) { comp.params.push({ idx: j, nome: "?", v: null }); }
        }
      }
      if (estourou && antC) for (let j = comp.params.length; j < antC.params.length; j++) comp.params.push(antC.params[j]);
      comps.push(comp);
    } catch (e) { comps.push({ idx: i, match: "?", nome: "?", params: [] }); }
  }
  if (estourou) CAPAC.disparos.funda_cortada_150ms = (CAPAC.disparos.funda_cortada_150ms || 0) + 1;
  return comps;
}

/* lista barata (so os matchNames) - varredura de fundo */
async function listaEfeitos(it) {
  const cadeia = await it.getComponentChain();
  const n = await aw(cadeia.getComponentCount());
  const out = [];
  for (let i = 0; i < n; i++) {
    try { out.push(String(await aw((await aw(cadeia.getComponentAtIndex(i))).getMatchName()))); } catch (_) { out.push("?"); }
  }
  return out;
}

function ehMatchTexto(m) { return /ADBE Text|Capsule|Graphic/i.test(m || ""); }
const INTRINSECOS = { "AE.ADBE Opacity": 1, "AE.ADBE Motion": 1, "AE.ADBE Time Remapping": 1 };

/* alinhamento de duas listas (LCS) -> [[i|null, j|null]] na ordem */
function alinhar(a, d) {
  const S = [];
  for (let i = 0; i <= a.length; i++) { S.push([]); for (let j = 0; j <= d.length; j++) S[i].push(0); }
  for (let i = a.length - 1; i >= 0; i--) for (let j = d.length - 1; j >= 0; j--)
    S[i][j] = a[i] === d[j] ? S[i + 1][j + 1] + 1 : Math.max(S[i + 1][j], S[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < a.length && j < d.length) {
    if (a[i] === d[j]) { out.push([i, j]); i++; j++; }
    else if (S[i + 1][j] >= S[i][j + 1]) { out.push([i, null]); i++; }
    else { out.push([null, j]); j++; }
  }
  while (i < a.length) { out.push([i, null]); i++; }
  while (j < d.length) { out.push([null, j]); j++; }
  return out;
}

function igual(x, y) { return JSON.stringify(x === undefined ? null : x) === JSON.stringify(y === undefined ? null : y); }

/* diferenca de efeitos de UM clipe (pura) */
function diffEfeitos(a, d) {
  const out = [];
  alinhar(a.map(function (c) { return c.match; }), d.map(function (c) { return c.match; })).forEach(function (par) {
    const ca = par[0] === null ? null : a[par[0]], cd = par[1] === null ? null : d[par[1]];
    if (!ca) { out.push({ mudanca: "colocou", efeito: { idx: cd.idx, match: cd.match, nome: cd.nome } }); return; }
    if (!cd) { out.push({ mudanca: "tirou", efeito: { idx: ca.idx, match: ca.match, nome: ca.nome } }); return; }
    const ef = { idx: cd.idx, match: cd.match, nome: cd.nome || ca.nome };
    const n = Math.max(ca.params.length, cd.params.length);
    for (let k = 0; k < n; k++) {
      const pa = ca.params[k], pd = cd.params[k];
      if (!pa || !pd) continue;
      const kfA = pa.kf ? { n: pa.nk, t: pa.kf, v: pa.kv } : null, kfD = pd.kf ? { n: pd.nk, t: pd.kf, v: pd.kv } : null;
      if (kfA || kfD) {
        if (!igual(kfA, kfD)) out.push({ mudanca: "keyframe", efeito: ef, param: { idx: pd.idx, nome: pd.nome || pa.nome,
          antes_n: kfA ? kfA.n : 0, depois_n: kfD ? kfD.n : 0, tempos: kfD ? kfD.t : [], valores: kfD ? kfD.v : [],
          antes_valor: kfA ? null : pa.v, depois_valor: kfD ? null : pd.v } });
        continue;
      }
      if (!igual(pa.v, pd.v)) out.push({ mudanca: "param", efeito: ef, param: { idx: pd.idx, nome: pd.nome || pa.nome, antes: pa.v, depois: pd.v } });
    }
  });
  return out;
}

/* in e vel vao junto: o resumo converte o tempo do KEYFRAME (que vem na midia, nao na timeline - SONDA 14/10 passo 3:
 * keyframes em 10,933 e 14,833 num clipe que ocupa 21,033-36,6 da timeline com in 5,467) pra timeline */
function itemCurto(rec) { return { faixa: rec.faixa, nome: rec.nome, inicio: rec.inicio, fim: rec.fim, in: rec.in, vel: rec.vel }; }

/* acha o objeto do clipe na faixa (objeto da ultima foto; senao pelo indice; confere inicio/fim) */
async function objetoDe(rec) {
  const est = atual && estadoSeq[atual.seqId];
  if (!est) return null;
  const o = est.objs[chaveClipe(rec)];
  const confere = async function (it) {
    try {
      const v = await Promise.all([it.getStartTime(), it.getEndTime()]);
      return perto(r3(seg(v[0])), rec.inicio) && perto(r3(seg(v[1])), rec.fim);
    } catch (_) { return false; }
  };
  if (o && o.it && await confere(o.it)) return o.it;
  try {
    const tipo = rec.faixa.charAt(0), i = Number(rec.faixa.slice(1)) - 1;
    const tr = tipo === "V" ? await atual.seq.getVideoTrack(i) : await atual.seq.getAudioTrack(i);
    const itens = (await aw(tr.getTrackItems(tipoClipe(), false))) || [];
    const k0 = o ? o.k : 0;
    for (let dk = 0; dk <= 3; dk++) {
      const ks = dk === 0 ? [k0] : [k0 + dk, k0 - dk];
      for (let q = 0; q < ks.length; q++) {
        const k = ks[q];
        if (k >= 0 && k < itens.length && await confere(itens[k])) return itens[k];
      }
    }
  } catch (_) {}
  return null;
}

function enfileirarFunda(rec, it, origem, ini) {
  const k = chaveClipe(rec);
  for (let i = 0; i < fundaFila.length; i++) {
    if (chaveClipe(fundaFila[i].rec) === k) {
      if (ini && (!fundaFila[i].ini || ini < fundaFila[i].ini)) fundaFila[i].ini = ini;
      if (it && !fundaFila[i].it) fundaFila[i].it = it;
      if (origem === "aviso") fundaFila[i].origem = "aviso";
      return;
    }
  }
  if (fundaFila.length < 40) fundaFila.push({ rec: rec, it: it, origem: origem, ini: ini });
}

function cabeFunda() {
  const agora = Date.now();
  while (fundas.length && fundas[0] < agora - 1000) fundas.shift();
  return fundas.length < MAX_FUNDAS_POR_S;
}

async function fundaDe(rec, it, origem, janelaIni) {
  if (MARCAS.efeitos === false) return;
  const k = chaveClipe(rec);
  if (!it) it = await objetoDe(rec);
  if (!it) return;
  const tLeitura = Date.now();
  fundas.push(tLeitura);
  let comps;
  const antes = efCache[k];
  const reusarKf = origem !== "aviso" && (CAPAC.disparos.faixa_mudou || 0) > 0;
  try { comps = await lerEfeitos(it, antes ? antes.comps : null, reusarKf); if (!MARCAS.efeitos) { MARCAS.efeitos = true; leituraOk("efeitos (getComponentChain)"); } }
  catch (e) {
    falhou("efeitos", 5);
    naoDisponivel("efeitos (getComponentChain)", e);
    return;
  }
  const agora = Date.now();
  comps.forEach(function (c) { if (ehMatchTexto(c.match)) ehTexto[k] = true; });
  const ant = efCache[k];
  efCache[k] = { comps: comps, ms: agora };
  const listaFundo = efLista[k + "#fundo"];
  efLista[k] = comps.map(function (c) { return c.match; });
  delete efLista[k + "#fundo"];
  let mud;
  if (ant) mud = diffEfeitos(ant.comps, comps);
  else if (listaFundo) {
    /* nunca lido fundo, mas a varredura de fundo sabia a lista: da pra dizer colocou/tirou */
    mud = diffEfeitos(listaFundo.map(function (m, i) { return { idx: i, match: m, nome: "", params: [] }; }),
                      comps.map(function (c) { return { idx: c.idx, match: c.match, nome: c.nome, params: [] }; }));
  } else if (origem === "aviso" && viaDrop && Math.abs(tLeitura - viaDrop) < 5000 && comps.length) {
    /* clipe nunca lido + efeito solto do painel agora: o efeito solto entra no FIM da cadeia (deducao) */
    const ult = comps[comps.length - 1];
    if (ult.idx >= 2 && !INTRINSECOS[ult.match]) mud = [{ mudanca: "colocou", efeito: { idx: ult.idx, match: ult.match, nome: ult.nome }, deducao: "ultimo_da_cadeia" }];
    else mud = [];
  } else mud = [];      // sem base: esta leitura vira a base (aviso de corte/trim tambem acorda isto)
  /* 18/10: a leitura de base que veio da varredura ("inicial") vai pro log inteira, compacta: [idx, valor] por ajuste
   * (+ tempos e valores dos keyframes quando tem). E o estado dos efeitos ANTES de ele mexer, que antes nao entrava. */
  if (!ant && origem === "inicial") {
    empurrar({ tipo: "efeito_inicial", item: itemCurto(rec), ms: tLeitura, carga: CARGA, origem: "inicial",
               comps: comps.map(function (c) { return { idx: c.idx, match: c.match, nome: c.nome,
                 p: c.params.map(function (q) { return q.kf ? [q.idx, q.v, q.kf, q.kv] : [q.idx, q.v]; }) }; }) });
  }
  if (!mud.length) return;
  leituraEf++;
  const ini = ant ? ant.ms : (janelaIni || agora);
  const msEv = janelaIni ? Math.max(ini, janelaIni) : tLeitura;   // com aviso: o 1o aviso; sem aviso: quando a leitura viu
  const base = { tipo: "efeito", item: itemCurto(rec), janela_ms: [ini, agora], carga: CARGA, leitura: leituraEf, origem: origem, ms: msEv };
  if (ant && ant.ms < ultimaRetomada) base.apos_pausa = true;
  let n = 0;
  mud.forEach(function (x) {
    if (n >= 40) return;
    /* texto: parametro de texto que mudou vira evento `texto` (fonte: parametro / mogrt) */
    if (x.mudanca === "param" && x.param && (typeof x.param.depois === "string" || (x.param.depois && x.param.depois.texto !== undefined))) {
      const dt = typeof x.param.depois === "string" ? x.param.depois : x.param.depois.texto;
      const at = (x.param.antes && x.param.antes.texto !== undefined) ? x.param.antes.texto : x.param.antes;
      if (ehMatchTexto(x.efeito.match) || (dt && dt.length > 0)) {
        empurrar({ tipo: "texto", mudanca: "editou", item: itemCurto(rec), antes: at, depois: dt,
                   fonte: (x.param.depois && x.param.depois.texto !== undefined) ? "mogrt" : "parametro",
                   efeito: x.efeito, janela_ms: base.janela_ms, ms: base.ms });
        n++;
        return;
      }
    }
    const ev = Object.assign({}, base, x);
    if (x.mudanca === "colocou" && viaDrop && agora - viaDrop < 5000) ev.via = "arrastou do painel";
    empurrar(ev);
    n++;
    /* desfazer provavel em efeito (camada 1): o valor voltou EXATAMENTE ao de antes da ultima mudanca */
    if (x.mudanca === "param") {
      const hk = k + "|" + x.efeito.match + "|" + x.param.idx;
      const h = efHist[hk] || (efHist[hk] = [{ v: x.param.antes, ms: ini }]);
      if (h.length >= 2 && igual(h[h.length - 2].v, x.param.depois) && agora - h[h.length - 1].ms <= 60000) {
        empurrar(Object.assign({}, base, { tipo: "desfazer_provavel", alvo: "efeito", efeito: x.efeito,
                                           param: { nome: x.param.nome, de: x.param.antes, voltou_a: x.param.depois } }));
      }
      h.push({ v: x.param.depois, ms: agora });
      if (h.length > 10) h.shift();
    }
  });
  if (mud.length > 40) empurrar(Object.assign({}, base, { mudanca: "varios", total: mud.length }));
}

/* clipes atingidos por um aviso de faixa: cruza o trecho com a ultima foto; trecho da faixa inteira
 * (efeito/mute) ou muitos clipes = os selecionados daquela faixa (e o que o Controle de Efeitos mostra) */
function atingidos(rot, s) {
  const est = atual && estadoSeq[atual.seqId];
  if (!est) return [];
  const naFaixa = est.itens.filter(function (x) { return x.faixa === rot; });
  let l = naFaixa;
  if (s.ini !== null && s.fim !== null) l = naFaixa.filter(function (x) { return x.inicio < s.fim - 0.001 && s.ini < x.fim - 0.001; });
  if (l.length <= 4 && l.length > 0) return l.map(function (x) { return { rec: x, it: null }; });
  return selObjs.filter(function (o) { return o.rec.faixa === rot; }).map(function (o) { return { rec: o.rec, it: o.it }; });
}

async function passoEfeitos() {
  if (!atual || !estadoSeq[atual.seqId] || MARCAS.efeitos === false) return false;
  if (tocandoAgora) return false;                              // tocando = adia
  if (!podeRodar("media")) return false;
  const agora = Date.now();
  let fez = false;
  const chaves = Object.keys(sujo);
  for (let i = 0; i < chaves.length; i++) {
    const rot = chaves[i], s = sujo[rot];
    if (!s || !(agora - s.ultimo >= SILENCIO_MS || agora - s.primeiro >= RAJADA_MAX_MS)) continue;
    delete sujo[rot];
    atingidos(rot, s).slice(0, 4).forEach(function (a) { enfileirarFunda(a.rec, a.it, "aviso", s.primeiro); });
  }
  /* fila de leituras fundas: o teto (3/s) e respeitado SEM dormir aqui dentro (o tempo dormindo
   * contaria como "lendo o Premiere" no orcamento); o que nao coube fica pra proxima volta. O orcamento e
   * reconferido a cada leitura (agora ele enxerga este proprio laco rodando) */
  while (fundaFila.length && cabeFunda() && podeRodar("media")) {
    const x = fundaFila.shift();
    await fundaDe(x.rec, x.it, x.origem, x.ini);
    fez = true;
  }
  /* 18/10: leitura de BASE (efeito_inicial), uma por volta, so quando nada de verdade esta pendente: fila funda vazia,
   * sem rajada de avisos (ele mexendo) e com folga no orcamento. Assim a base nunca empurra uma leitura de mudanca. */
  /* ...e nunca no lugar da rede do clipe SELECIONADO (a base dele vem primeiro: e nele que ele vai mexer), no maximo 1 por
   * segundo e so com o orcamento de leituras fundas VAZIO no ultimo segundo (sobra tudo pras leituras de mudanca) */
  const redeSelDevida = selObjs.length && agora - ultimaFundaSel >= ((CAPAC.disparos.faixa_mudou || 0) > 0 ? T_EFEITOS_SEL_COM_AVISO : T_EFEITOS_SEL);
  if (!fez && !fundaFila.length && filaIni.length && !redeSelDevida && agora - ultimaIni >= 1000 && (cabeFunda(), fundas.length === 0) && !(agora - ultimoAvisoFaixa < SILENCIO_MS || Object.keys(sujo).length > 0) && cabeFunda() && podeRodar("baixa")) {
    ultimaIni = agora;
    const x = filaIni.shift();
    if (!efCache[chaveClipe(x.rec)]) { await fundaDe(x.rec, x.it, "inicial", null); fez = true; }
  }
  /* rede de 2 s do clipe selecionado: NUNCA no meio de uma rajada de avisos (leria o slider no meio do
   * arrasto e o ajuste sairia partido em dois); depois do silencio o aviso ja manda ler */
  const emRajada = agora - ultimoAvisoFaixa < SILENCIO_MS || Object.keys(sujo).length > 0;
  /* com o aviso de faixa CHEGANDO (mexer no efeito dispara aviso), a rede do selecionado so a cada 15 s
   * (relia o clipe inteiro a cada 2 s pra sempre: ~4% fixo com Lumetri - REVISAO-desempenho 4) */
  const redeSel = (CAPAC.disparos.faixa_mudou || 0) > 0 ? T_EFEITOS_SEL_COM_AVISO : T_EFEITOS_SEL;
  if (selObjs.length && !emRajada && agora - ultimaFundaSel >= redeSel && cabeFunda() && podeRodar("media")) {
    ultimaFundaSel = agora;
    /* o clipe selecionado (o video e, se vinculado, o audio dele) */
    const primeiro = selObjs[0];
    for (let i = 0; i < selObjs.length && i < 2; i++) {
      const o = selObjs[i];
      if (i > 0 && (o.rec.nome !== primeiro.rec.nome || !perto(o.rec.inicio, primeiro.rec.inicio))) break;
      if (!cabeFunda()) break;
      await fundaDe(o.rec, o.it, "selecionado", null);
      fez = true;
    }
  }
  return fez;
}

/* varredura de fundo: lista de efeitos de todos os clipes (rodizio), marcadores dos mestres, legendas */
async function passoFundo() {
  if (!atual || !podeRodar("baixa")) return false;
  const agora = Date.now();
  if (agora - ultimoFundo < T_FUNDO) return false;
  ultimoFundo = agora;
  const est = estadoSeq[atual.seqId];
  if (!est) return false;
  if (MARCAS.efeitos !== false) {
    const l = est.itens;
    for (let n = 0; n < FUNDO_CLIPES_POR_VOLTA && l.length; n++) {
      if (!podeRodar("baixa")) break;
      rodizioFundo = (rodizioFundo + 1) % l.length;
      const rec = l[rodizioFundo];
      const k = chaveClipe(rec);
      const o = est.objs[k];
      if (!o || !o.it) continue;
      let lista;
      try { lista = await listaEfeitos(o.it); } catch (_) { continue; }
      lista.forEach(function (m) { if (ehMatchTexto(m)) ehTexto[k] = true; });
      const antL = efLista[k];
      /* 18/10 (pedido dele: "registro 100%"): clipe visto pela 1a vez = tambem leitura FUNDA de base (origem "inicial"),
       * que sai no log como "efeito_inicial" com o valor de cada ajuste (volume, escala, Lumetri...) de ANTES de ele mexer */
      if (!antL) { efLista[k] = lista; if (!efCache[k]) { efLista[k + "#fundo"] = lista; if (!filaIniVista[k]) { filaIniVista[k] = 1; filaIni.push({ rec: rec, it: o.it }); } } continue; }
      if (igual(antL, lista)) continue;
      if (efCache[k]) { enfileirarFunda(rec, null, "varredura", null); continue; }       // ja tem leitura funda: a funda conta o que mudou
      efLista[k] = lista;
      efLista[k + "#fundo"] = lista;
      leituraEf++;
      alinhar(antL, lista).forEach(function (par) {
        if (par[0] !== null && par[1] !== null) return;
        const colocou = par[0] === null;
        const m = colocou ? lista[par[1]] : antL[par[0]];
        const ev = { tipo: "efeito", mudanca: colocou ? "colocou" : "tirou", item: itemCurto(rec), efeito: { idx: colocou ? par[1] : par[0], match: m, nome: "" },
                     janela_ms: [agora - T_FUNDO * Math.ceil(l.length / FUNDO_CLIPES_POR_VOLTA), agora], carga: CARGA, leitura: leituraEf, origem: "varredura" };
        if (colocou && viaDrop && agora - viaDrop < 60000) ev.via = "arrastou do painel";
        empurrar(ev);
      });
    }
  }
  /* marcadores dos mestres da timeline (marcador feito no monitor de origem ou em clipe nao selecionado) */
  const pids = Object.keys(est.usos);
  if (fonteAtual && mestres[fonteAtual] && pids.indexOf(fonteAtual) < 0) pids.push(fonteAtual);
  for (let n = 0; n < FUNDO_MESTRES_POR_VOLTA && pids.length && MARCAS.marcClipe !== false; n++) {
    if (!podeRodar("baixa")) break;
    rodizioMestres = (rodizioMestres + 1) % pids.length;
    await lerMarcadoresMestre(pids[rodizioMestres], "varredura");
  }
  if ((legLeitura || agora - ultimaLeg >= T_LEGENDAS) && podeRodar("baixa")) { if (!legLeitura) ultimaLeg = agora; await passoLegendas(est); }
  return true;
}

/* legendas: posicoes so quando a contagem mudou (podem ser centenas). O TEXTO nao e legivel no 26.5.2. */
async function passoLegendas(est) {
  if (MARCAS.legendas === false || !est.faixas.L.length) { legLeitura = null; return; }
  const sigCont = est.faixas.L.map(function (x) { return x.n; }).join(",");
  const ant = legPos[atual.seqId];
  if (!legLeitura || legLeitura.seqId !== atual.seqId || legLeitura.sig !== sigCont) {
    if (ant && ant.sig === sigCont) { legLeitura = null; return; }
    legLeitura = { seqId: atual.seqId, sig: sigCont, j: 0, k: 0, lista: [] };
  }
  const L = legLeitura, t0 = Date.now();
  try {
    while (L.j < est.faixas.L.length) {
      const ct = await atual.seq.getCaptionTrack(L.j);
      const itens = (await aw(ct.getTrackItems(tipoClipe(), false))) || [];
      while (L.k < itens.length && L.k < 2000) {
        const lote = itens.slice(L.k, Math.min(itens.length, L.k + 50, 2000));
        const vs = await Promise.all(lote.map(function (x) { return Promise.all([x.getStartTime(), x.getEndTime()]); }));
        vs.forEach(function (v) { L.lista.push({ faixa: "L" + (L.j + 1), inicio: r3(seg(v[0])), fim: r3(seg(v[1])) }); });
        L.k += lote.length;
        if (Date.now() - t0 > T_LEG_MAX) return;          // continua na proxima volta do fundo
      }
      L.j++; L.k = 0;
    }
    leituraOk("legendas (tempos)");
  } catch (e) { legLeitura = null; naoDisponivel("legendas (itens/tempos)", e); return; }
  legLeitura = null;
  const lista = L.lista;
  const agora = Date.now();
  if (ant) {
    const k = function (x) { return x.faixa + "|" + x.inicio + "|" + x.fim; };
    const ma = {}; ant.lista.forEach(function (x) { ma[k(x)] = x; });
    const md = {}; lista.forEach(function (x) { md[k(x)] = x; });
    const novas = lista.filter(function (x) { return !ma[k(x)]; });
    const sumidas = ant.lista.filter(function (x) { return !md[k(x)]; });
    const usadas = {};
    novas.forEach(function (d) {
      let par = -1;
      for (let i = 0; i < sumidas.length; i++) if (!usadas[i] && sumidas[i].faixa === d.faixa && sumidas[i].inicio < d.fim && d.inicio < sumidas[i].fim) { par = i; break; }
      if (par >= 0) { usadas[par] = true; empurrar({ tipo: "legenda", mudanca: "mudou", faixa: d.faixa, inicio: d.inicio, fim: d.fim, antes: sumidas[par], janela_ms: [ant.ms, agora] }); }
      else empurrar({ tipo: "legenda", mudanca: "nova", faixa: d.faixa, inicio: d.inicio, fim: d.fim, janela_ms: [ant.ms, agora] });
    });
    sumidas.forEach(function (x, i) { if (!usadas[i]) empurrar({ tipo: "legenda", mudanca: "apagada", faixa: x.faixa, inicio: x.inicio, fim: x.fim, janela_ms: [ant.ms, agora] }); });
  }
  legPos[atual.seqId] = { sig: sigCont, lista: lista, ms: agora };
}

/* ------------------------------------------------------------ projeto (item 2) */
function tipoProj(nome) { try { return ppro.ProjectItem ? ppro.ProjectItem[nome] : undefined; } catch (_) { return undefined; } }

async function idsDasSequencias(proj) {
  const ids = {};
  const seqs = (await aw(proj.getSequences())) || [];
  for (let i = 0; i < seqs.length; i++) {
    try { const pi = await seqs[i].getProjectItem(); const id = await idDe(pi); if (id) ids[id] = true; } catch (_) {}
  }
  return ids;
}

async function lerArvore(proj) {
  const TB = tipoProj("TYPE_BIN"), TC = tipoProj("TYPE_CLIP");
  const raiz = await proj.getRootItem();
  const out = {}, objs = {};
  const rid = (await idDe(raiz)) || "raiz";
  const pendentes = [{ f: raiz, id: rid, caminho: "" }];
  let bins = 0, contados = 0;
  while (pendentes.length) {
    const x = pendentes.shift();
    let itens;
    try {
      if (typeof x.f.getItems === "function") itens = await aw(x.f.getItems());
      else itens = await aw((await aw(ppro.FolderItem.cast(x.f))).getItems());
    } catch (_) { continue; }
    itens = itens || [];
    for (let i = 0; i < itens.length; i++) {
      const it = itens[i];
      if (++contados % 300 === 0) await dormir(0);      // bin de milhares de itens: solta o fio de vez em quando
      try {
        const id = await idDe(it);
        if (!id) continue;
        let nome = "", tp = null;
        try { nome = it.name || ""; } catch (_) {}
        try { tp = it.type; } catch (_) {}
        const ehBin = TB !== undefined && tp === TB;
        const tipo = ehBin ? "bin" : ((projSeqIds && projSeqIds[id]) ? "sequencia" : ((TC === undefined || tp === TC) ? "midia" : "outro"));
        out[id] = { id: id, nome: nome, tipo: tipo, pai: x.id, bin: x.caminho || "(raiz)" };
        objs[id] = it;
        if (ehBin) {
          bins++;
          let pasta = it;
          try { if (ppro.FolderItem && ppro.FolderItem.cast) pasta = (await aw(ppro.FolderItem.cast(it))) || it; } catch (_) {}
          pendentes.push({ f: pasta, id: id, caminho: (x.caminho ? x.caminho + "/" : "") + nome });
        }
      } catch (_) {}
    }
  }
  return { itens: out, objs: objs, bins: bins };
}

/* diferenca da arvore do projeto (pura): por id; pai = id do bin (renomear bin nao vira "moveu") */
function diffProjeto(a, d) {
  const out = [];
  const rem = {};
  Object.keys(a).forEach(function (id) { if (!d[id]) rem[id] = true; });
  const filhosRem = {};
  Object.keys(rem).forEach(function (id) {
    let p = a[id].pai, topo = id;
    while (p && rem[p]) { topo = p; p = a[p].pai; }
    if (topo !== id) filhosRem[topo] = (filhosRem[topo] || 0) + 1;
  });
  Object.keys(rem).forEach(function (id) {
    const p = a[id].pai;
    if (p && rem[p]) return;              // some junto com o bin pai: conta no conteudo dele
    const x = { mudanca: "apagou", item: { id: id, nome: a[id].nome, tipo: a[id].tipo, bin: a[id].bin } };
    if (filhosRem[id]) x.conteudo = filhosRem[id];
    out.push(x);
  });
  /* item novo dentro de bin novo (importou uma pasta / Ctrl+Z de um bin apagado) = conta no bin */
  const filhosNovos = {};
  Object.keys(d).forEach(function (id) {
    if (a[id]) return;
    let p = d[id].pai, topo = id;
    while (p && d[p] && !a[p]) { topo = p; p = d[p].pai; }
    if (topo !== id) (filhosNovos[topo] = filhosNovos[topo] || []).push(d[id].nome);
  });
  Object.keys(d).forEach(function (id) {
    const x = d[id], y = a[id];
    if (!y) {
      if (x.pai && d[x.pai] && !a[x.pai]) return;          // conta no conteudo do bin novo
      const m = x.tipo === "midia" ? "importou" : x.tipo === "bin" ? "criou_bin" : x.tipo === "sequencia" ? "criou_sequencia" : "novo";
      const ev = { mudanca: m, item: { id: id, nome: x.nome, tipo: x.tipo, bin: x.bin } };
      if (filhosNovos[id]) { ev.conteudo = filhosNovos[id].length; ev.filhos = filhosNovos[id].slice(0, 20); }
      out.push(ev);
      return;
    }
    if (x.nome !== y.nome) out.push({ mudanca: "renomeou", item: { id: id, nome: x.nome, tipo: x.tipo, bin: x.bin }, antes: { nome: y.nome } });
    if (x.pai !== y.pai) out.push({ mudanca: "moveu", item: { id: id, nome: x.nome, tipo: x.tipo, bin: x.bin }, antes: { bin: y.bin } });
  });
  return out;
}

function chaveDoProjeto(proj) {
  try { const g = proj.guid; if (g) return "guid:" + str(g); } catch (_) {}
  try { if (proj.path) return "path:" + proj.path; } catch (_) {}
  try { return "nome:" + (proj.name || "?"); } catch (_) { return "?"; }
}

function nomeOperacao(estado) {
  /* nome do OperationCompleteState (SUCCESS/CANCELLED/FAILED) - compara com as constantes, nao com 0 (REVISAO-api 11) */
  try {
    const g = ppro.Constants && ppro.Constants.OperationCompleteState;
    if (g) { const ks = Object.keys(g); for (let i = 0; i < ks.length; i++) if (g[ks[i]] === estado) return ks[i]; }
  } catch (_) {}
  return null;
}

async function lerProjeto() {
  let proj = atual && atual.proj;
  if (!proj) { try { proj = await ppro.Project.getActiveProject(); } catch (_) {} }
  if (!proj) return;
  /* 2 projetos abertos: cada um tem a sua foto (trocar pra sequencia do outro projeto comparava a arvore do A
   * com a do B e saiam centenas de "apagou/importou" falsos - REVISAO-api 8) */
  const ch = chaveDoProjeto(proj);
  if (projChave !== null && ch !== projChave) {
    projEstados[projChave] = { foto: projFoto, seqIds: projSeqIds, lento: projLento, ms: projMsLeitura };
    const v = projEstados[ch];
    projFoto = v ? v.foto : null; projSeqIds = v ? v.seqIds : null; projLento = v ? v.lento : false; projMsLeitura = v ? v.ms : 0;
    projImport = null;
  }
  projChave = ch;
  const t0 = Date.now();
  const sujoAntes = projSujo;
  const dirtyAntes = projDirty;
  let r;
  try {
    if (!projSeqIds) projSeqIds = await idsDasSequencias(proj);
    r = await lerArvore(proj);
    if (!MARCAS.projeto) { MARCAS.projeto = true; leituraOk("projeto (arvore de bins)"); }
  } catch (e) {
    falhou("projeto", 3);
    naoDisponivel("projeto (getRootItem/getItems)", e);
    projUltima = Date.now();
    return;
  }
  /* item novo: confere se e sequencia (lista de sequencias mudou) e o caminho da midia */
  const novos = projFoto ? Object.keys(r.itens).filter(function (id) { return !projFoto[id]; }) : [];
  if (novos.length) {
    try { projSeqIds = await idsDasSequencias(proj); } catch (_) {}
    for (let i = 0; i < novos.length && i < 200; i++) {
      const x = r.itens[novos[i]];
      if (x.tipo === "bin") continue;
      if (projSeqIds && projSeqIds[x.id]) { x.tipo = "sequencia"; continue; }
      try { x.caminho = await caminhoDe(r.objs[x.id]); } catch (_) {}
    }
  }
  /* guarda o caminho ja conhecido dos itens antigos */
  if (projFoto) Object.keys(r.itens).forEach(function (id) {
    if (projFoto[id] && projFoto[id].caminho && !r.itens[id].caminho) r.itens[id].caminho = projFoto[id].caminho;
    if (projFoto[id] && projFoto[id].tipo === "sequencia" && r.itens[id].tipo !== "bin") r.itens[id].tipo = "sequencia";
  });
  const agora = Date.now();
  const ms = agora - t0;
  projMsLeitura = ms;
  if (!projFoto) {
    const l = Object.keys(r.itens).map(function (k) { return r.itens[k]; });
    let nomeProj = "";
    try { nomeProj = proj.name || ""; } catch (_) {}
    empurrar({ tipo: "projeto_inicial", projeto: nomeProj, total: l.length, bins: r.bins,
               sequencias: l.filter(function (x) { return x.tipo === "sequencia"; }).length,
               midias: l.filter(function (x) { return x.tipo === "midia"; }).length, ms_leitura: ms, ms: t0 });
    if (ms > 300) { projLento = true; logar("aviso", "projeto grande: leitura da árvore levou " + ms + " ms (segurança passa a cada 60 s)"); }
  } else {
    const mud = diffProjeto(projFoto, r.itens);
    if (mud.length) {
      projN++;
      const marcas = [sujoAntes, dirtyAntes].filter(function (x) { return x && x > projUltima; });
      const base = { tipo: "projeto", janela_ms: [projUltima, t0], carga: CARGA, leitura: projN, ms: marcas.length ? Math.min.apply(null, marcas) : t0 };
      if (projUltima < ultimaRetomada) base.apos_pausa = true;
      if (projImport && projImport.ms >= projUltima) {
        const op = nomeOperacao(projImport.estado);
        base.operacao = (projImport.estado === null || projImport.estado === undefined || op === "SUCCESS") ? "import_ok"
          : "import_" + (op ? op.toLowerCase() : "estado_" + projImport.estado);
      }
      mud.slice(0, 300).forEach(function (x) {
        if (x.mudanca !== "apagou" && r.itens[x.item.id] && r.itens[x.item.id].caminho) x.item.caminho = r.itens[x.item.id].caminho;
        empurrar(Object.assign({}, base, x));
      });
      if (mud.length > 300) empurrar(Object.assign({}, base, { mudanca: "varios", total: mud.length }));
    }
  }
  projFoto = r.itens;
  projUltima = Date.now();
  projDirtyVisto = Math.max(projDirtyVisto, dirtyAntes);
  if (projImport && projImport.ms < t0) projImport = null;
}

async function passoProjeto() {
  if (MARCAS.projeto === false || tocandoAgora) return false;      // nunca durante o play
  const agora = Date.now();
  const minimo = Math.max(500, 4 * projMsLeitura);                  // nunca mais que 25% do tempo na arvore
  /* DIRTY colado (1 s) num aviso de faixa = edicao de TIMELINE: nao acorda a arvore (REVISAO-desempenho 2) */
  if (projDirty > projDirtyVisto && agora - projDirty >= 1000 &&
      avisosFaixa.some(function (t) { return Math.abs(t - projDirty) < 1000; })) projDirtyVisto = projDirty;
  const dirtySozinho = projDirty > projDirtyVisto && projDirty > projUltima && agora - projDirty >= 1000;
  const sujoAgora = projSujo && projSujo > projUltima && agora - projSujo >= 500;
  let vez = false, prio = "media";
  if (!projFoto) vez = agora - projUltima >= 3000;
  else if ((sujoAgora || dirtySozinho) && agora - projUltima >= minimo) vez = true;
  else if (agora - ultimoCliqueProj < JANELA_CLIQUE && agora - projUltima >= Math.max(T_PROJ_CLIQUE, 4 * projMsLeitura)) vez = true;
  else {
    /* seguranca (rede caso um aviso escape): o DIRTY dispara a CADA mudanca no 26.5.2 (SONDA 14/10), entao arvore
     * barata (<= 30 ms) ou grande = 15 s; muito grande (> 300 ms) = 60 s. (Antes da sonda a barata era 3 s.) */
    const barata = projMsLeitura <= PROJ_BARATO_MS;
    const seg = projLento ? T_PROJ_LENTO : (barata ? T_PROJ_BARATO : T_PROJ_SEGURANCA);
    if (agora - projUltima >= Math.max(seg, minimo)) { vez = true; prio = barata ? "media" : "baixa"; }
  }
  if (!vez || !podeRodar(prio)) return false;
  await lerProjeto();
  return true;
}

/* ------------------------------------------------------------ monitor de origem (extra) */
async function passoFonte() {
  if (MARCAS.fonte === false) return false;
  if (!ppro.SourceMonitor || typeof ppro.SourceMonitor.getProjectItem !== "function") { MARCAS.fonte = false; CAPAC.existe.SourceMonitor = false; return false; }
  const agora = Date.now();
  if (agora - ultimaFonte < T_FONTE || !podeRodar("media")) return false;
  ultimaFonte = agora;
  let pi;
  try { pi = await ppro.SourceMonitor.getProjectItem(); if (!MARCAS.fonte) { MARCAS.fonte = true; leituraOk("monitor de origem"); } }
  catch (e) {
    /* monitor de origem vazio pode responder com erro: so registra (uma vez) e segue tentando */
    fonteAtual = null;
    naoDisponivel("monitor de origem (SourceMonitor.getProjectItem)", e);
    return true;
  }
  if (!pi) { fonteAtual = null; return true; }
  const id = await idDe(pi);
  if (!id || id === fonteAtual) return true;
  fonteAtual = id;
  let nome = "";
  try { nome = pi.name || ""; } catch (_) {}
  const caminho = await caminhoDe(pi);
  if (!mestres[id]) mestres[id] = { pi: pi, nome: nome, caminho: caminho };
  let pos = null;
  try { pos = r3(seg(await ppro.SourceMonitor.getPosition())); } catch (_) {}
  empurrar({ tipo: "fonte", id: id, nome: nome, caminho: caminho, pos: pos });
  return true;
}

/* ------------------------------------------------------------ fila de avisos baratos (eventos) */
async function passoEventos() {
  const agora = Date.now();
  let fez = false;
  /* cadeado (so alternancia: a API nao diz se travou ou destravou) */
  if (pendTrava.length) {
    const vistos = {};
    pendTrava.splice(0).forEach(function (p) {
      if (vistos[p.faixa] && p.ms - vistos[p.faixa] < 300) return;
      vistos[p.faixa] = p.ms;
      empurrar({ tipo: "faixa", mudanca: "trava_alternou", faixa: p.faixa, ms: p.ms });
    });
    fez = true;
  }
  /* mute relampago: so o isMuted da faixa avisada (roda ate tocando) */
  if (MARCAS.mute !== false && atual && estadoSeq[atual.seqId]) {
    const est = estadoSeq[atual.seqId];
    const ks = Object.keys(muteSujo).filter(function (k) { return agora - muteSujo[k] >= 150; }).slice(0, 4);
    for (let i = 0; i < ks.length; i++) {
      const rot = ks[i];
      delete muteSujo[rot];
      const tipo = rot.charAt(0), idx = Number(rot.slice(1)) - 1;
      const info = est.faixas[tipo] && est.faixas[tipo][idx];
      if (!info) continue;
      try {
        const tr = tipo === "V" ? await atual.seq.getVideoTrack(idx) : await atual.seq.getAudioTrack(idx);
        const m = !!(await tr.isMuted());
        const agoraEst = atual && estadoSeq[atual.seqId];
        const inf = agoraEst && agoraEst.faixas[tipo] && agoraEst.faixas[tipo][idx];
        if (inf && inf.mudo !== null && inf.mudo !== undefined && m !== inf.mudo) {
          empurrar({ tipo: "faixa", mudanca: "mute", faixa: rot, antes: inf.mudo, depois: m, fonte: "aviso" });
        }
        if (inf) inf.mudo = m;
      } catch (_) {}
      fez = true;
    }
  }
  /* export (Premiere e Media Encoder) */
  if (pendExport.length) {
    const l = pendExport.splice(0);
    for (let i = 0; i < l.length; i++) {
      const p = l[i];
      const ev = Object.assign({ tipo: "export" }, p);
      if (p.fase === "progresso") {
        const q = Math.floor((p.progresso || 0) * 4);
        if (encoderJobs[p.job] !== undefined && q <= encoderJobs[p.job]) continue;
        encoderJobs[p.job] = q;
      } else if (p.via === "media_encoder") {
        /* os dois nomes de aviso do Media Encoder podem disparar juntos: o mesmo job + fase conta 1 vez */
        const kj = (p.job !== undefined ? p.job : "?") + "|" + p.fase;
        if (encoderVistos[kj] && (p.job !== undefined || p.ms - encoderVistos[kj] < 2000)) continue;
        encoderVistos[kj] = p.ms;
      }
      if (p.via === "premiere" && p.estado !== null && p.estado !== undefined) {
        const op = nomeOperacao(p.estado);
        if (op) { ev.estado = op; ev.sucesso = op === "SUCCESS"; }
      }
      if (p.via === "premiere" && atual) {
        try {
          const io = await Promise.all([atual.seq.getInPoint(), atual.seq.getOutPoint(), tentar(function () { return atual.seq.getEndTime(); })]);
          ev.trecho = { in: tempoMarcado(io[0]), out: tempoMarcado(io[1]), fim: io[2].v ? r3(seg(io[2].v)) : null };
        } catch (_) {}
        try {
          if (ppro.WorkAreaUtils) {
            const wi = await aw(ppro.WorkAreaUtils.getWorkAreaInPoint(atual.seq)), wo = await aw(ppro.WorkAreaUtils.getWorkAreaOutPoint(atual.seq));
            ev.area_trabalho = { in: r3(seg(wi)), out: r3(seg(wo)) };
          }
        } catch (_) {}
        ev.sequencia = atual.nome;
      }
      empurrar(ev);
    }
    fez = true;
  }
  /* clique no painel Projeto: junta cliques a cada 300 ms */
  if (pendClique && agora - pendClique.ms >= 300) {
    const p = pendClique;
    pendClique = null;
    const itens = [];
    let total = 0;
    try {
      let l = p.itens ? [].concat(p.itens) : null;
      /* SONDA 14/10: o aviso chegou sem campo visivel -> pergunta a selecao ao ProjectUtils (existe no 26.5.2 e
       * respondeu sem erro na sonda; com itens de verdade so a fase B confirma). 1 leitura por clique (juntados a cada 300 ms) */
      if (!l && ppro.ProjectUtils && typeof ppro.ProjectUtils.getSelection === "function" && MARCAS.selProj !== false) {
        try {
          const proj = (atual && atual.proj) || await ppro.Project.getActiveProject();
          const sel = proj ? await aw(ppro.ProjectUtils.getSelection(proj)) : null;
          l = sel ? [].concat((await aw(sel.getItems())) || []) : [];
          if (!MARCAS.selProj) { MARCAS.selProj = true; leituraOk("seleção do painel Projeto"); }
        } catch (e) { falhou("selProj", 3); naoDisponivel("seleção do painel Projeto (ProjectUtils.getSelection)", e); }
      }
      l = l || [];
      total = l.length;
      const TB = tipoProj("TYPE_BIN");
      for (let i = 0; i < l.length && i < 20; i++) {
        let nome = "", tp = "item";
        try { nome = l[i].name || ""; } catch (_) {}
        try { if (TB !== undefined && l[i].type === TB) tp = "bin"; } catch (_) {}
        if (projFoto) { const id = await idDe(l[i]); if (id && projFoto[id]) tp = projFoto[id].tipo; }
        itens.push({ nome: nome, tipo: tp });
      }
    } catch (_) {}
    const sig = JSON.stringify(itens);
    if (sig !== ultimoCliqueSig) { ultimoCliqueSig = sig; empurrar({ tipo: "projeto_selecao", itens: itens, total: total, ms: p.ms }); }
    fez = true;
  }
  /* navalha / limite da midia (no maximo 1 a cada 5 s por tipo) */
  if (pendFerramenta.length) {
    pendFerramenta.splice(0).forEach(function (p) {
      const ult = ultimaFerramenta[p.qual];
      ultimaFerramenta[p.qual] = p.ms;
      if (ult && p.ms - ult < 5000) return;
      empurrar({ tipo: "ferramenta", qual: p.qual, ms: p.ms });
    });
  }
  if (pendDesfazer.length) {
    pendDesfazer.splice(0).forEach(function (p) { empurrar({ tipo: "desfazer", fonte: "evento", qual: p.qual, nome: p.nome, ms: p.ms }); });
  }
  return fez;
}

/* ------------------------------------------------------------ lacos */
/* laco encadeado com guarda: nunca empilha leituras. Erro de laco NOVO (nivel "aviso") nao pinta
 * o painel de vermelho: so o que ja existia no 0.1 (agulha, selecao, foto) avisa como erro. */
function laco(nome, fn, intervalo, g, nivelErro) {
  const vez = async function () {
    if (g !== geracao || !capturando) return;
    const t0 = Date.now();
    const D = DES;
    inicioLeitura(D);
    try { await fn(); } catch (e) { logar(nivelErro || "erro", nome + ": " + msgErro(e)); }
    finally { fimLeitura(D); }
    if (g !== geracao || !capturando) return;
    const gasto = Date.now() - t0;
    registrar(nome, gasto);
    setTimeout(vez, Math.max(40, intervalo(gasto) - gasto));
  };
  setTimeout(vez, 0);
}

function emitirCapacidades(fase) {
  const ev = { tipo: "capacidades", fase: fase, versao: VERSAO, ouvintes: Object.assign({}, CAPAC.ouvintes),
               existe: Object.assign({}, CAPAC.existe), leituras: Object.assign({}, CAPAC.leituras) };
  if (fase === "fim") { ev.campos = CAPAC.campos; ev.disparos = CAPAC.disparos; }
  empurrar(ev);
}

function comecarCaptura() {
  capturando = true;
  geracao++;
  const g = geracao;
  if (DES && DES.desde === null) DES.desde = Date.now();
  try {
    CAPAC.existe.MogrtText = !!ppro.MogrtText;
    CAPAC.existe.WorkAreaUtils = !!ppro.WorkAreaUtils;
    CAPAC.existe.SourceMonitor = !!ppro.SourceMonitor;
    CAPAC.existe.EventManager = !!ppro.EventManager;
  } catch (_) {}
  ligarOuvintes(g).catch(function (e) { naoDisponivel("ouvintes", e); }).then(function () {
    if (g === geracao && capturando && !capacEmitida) { capacEmitida = true; emitirCapacidades("inicio"); }
  });
  laco("agulha", passoAgulha, function () { return T_AGULHA; }, g);
  laco("selecao", passoSelecaoTick, function () { return 100; }, g);
  laco("foto", passoFoto, function () { return 100; }, g);
  laco("marcadores", passoMarcadores, function () { return T_MARCADORES; }, g, "aviso");
  laco("eventos", passoEventos, function () { return T_EVENTOS; }, g, "aviso");
  laco("efeitos", passoEfeitos, function () { return 150; }, g, "aviso");
  laco("projeto", passoProjeto, function () { return 250; }, g, "aviso");
  laco("fonte", passoFonte, function () { return 250; }, g, "aviso");
  laco("fundo", passoFundo, function () { return 500; }, g, "aviso");
  laco("desempenho", async function () {
    if (Date.now() - DES.ultimoLog < 60000) return;
    DES.ultimoLog = Date.now();
    const r = resumoDesempenho();
    logar("info", "desempenho: " + Math.round(r.ocupacao_media * 100) + "% do tempo lendo em média, pico " +
          Math.round(r.ocupacao_pico * 100) + "% (" + r.pico_laco + ") · " +
          Object.keys(r.lacos).map(function (k) { return k + " " + r.lacos[k].media_ms + "/" + r.lacos[k].pico_ms + " ms"; }).join(", "));
  }, function () { return 5000; }, g, "aviso");
}

function pararCaptura() {
  capturando = false;
  geracao++;
  calar();
  if (DES && DES.desde !== null) { DES.capt_ms += Date.now() - DES.desde; DES.desde = null; }
}

function zerar() {
  atual = null; ag = null; velAnt = null; agEmitida = null; selSig = null; selBarata = null; tocandoAgora = false;
  fotoN = 0; aposPausa = false; retomadaPendente = false; fimUltimaFoto = 0; avisouLenta = false;
  fotoProxima = 0; fotoMinima = 0; fotoAcordada = 0; ultimaRetomada = 0;
  estadoSeq = {}; historico = {}; marcasSeq = {}; marcasClipe = {}; mestres = {}; ultimaMarcSeq = 0; rodizioMestres = 0;
  selMestres = []; selObjs = []; selSuja = 0; selInicio = 0; sujo = {}; muteSujo = {}; ultimoAvisoFaixa = 0;
  pendTrava = []; pendExport = []; pendFerramenta = []; pendDesfazer = []; pendClique = null; ultimoCliqueSig = null; ultimaFerramenta = {};
  viaDrop = 0; efCache = {}; efLista = {}; efHist = {}; ehTexto = {}; fundaFila = []; filaIni = []; filaIniVista = {}; ultimaIni = 0; fundas = []; leituraEf = 0; ultimaFundaSel = 0;
  rodizioFundo = 0; ultimoFundo = 0; projFoto = null; projSeqIds = null; projSujo = 0; projUltima = 0; projN = 0; projImport = null;
  projLento = false; projMsLeitura = 0; ultimoCliqueProj = 0; fonteAtual = null; ultimaFonte = 0; legPos = {}; ultimaLeg = 0; encoderJobs = {};
  capacEmitida = false; perdidos = 0; faixasLigadas = null;
  ultimaFotoMs = 0; selSujaPrimeiro = 0; avisosFaixa = []; projChave = null; projEstados = {}; projDirty = 0; projDirtyVisto = 0;
  legLeitura = null; ultimaContLeg = 0; rodizioSelMestre = 0; encoderVistos = {};
  Object.keys(ritmoMarc).forEach(function (k) { delete ritmoMarc[k]; });
  CAPAC = { ouvintes: {}, leituras: {}, existe: {}, campos: {}, disparos: {} };
  Object.keys(MARCAS).forEach(function (k) { MARCAS[k] = null; });
  Object.keys(AVISADOS).forEach(function (k) { delete AVISADOS[k]; });
  zerarDesempenho();
}

/* ultima leitura antes de pausar/concluir: pega a mudanca feita no ultimo segundo */
async function fotoFinal(prazo) {
  const t0 = Date.now();
  while (fotoRodando && Date.now() - t0 < prazo) await dormir(50);
  if (fotoRodando || !atual) return;
  await Promise.race([(async function () {
    try { await tirarFoto(); } catch (e) { logar("erro", "foto final: " + msgErro(e)); }
    try { await passoMarcadores(); } catch (_) {}
    try { await passoEventos(); } catch (_) {}
  })(), dormir(prazo)]);
}

function fecharRegistro() {
  try { empurrar(Object.assign({ tipo: "desempenho" }, resumoDesempenho())); } catch (_) {}
  try { emitirCapacidades("fim"); } catch (_) {}
}

/* ------------------------------------------------------------ acoes (clique = comando remoto) */
function aplicarStatus(r) {
  servidor = Object.assign({}, servidor || {}, r);
  tRecebido = Date.now();
}

async function iniciar() {
  if (ocupado || !servidor || servidor.estado !== "parado") return;
  ocupado = true;
  try {
    let c = null;
    try { c = await lerContexto(); } catch (_) {}
    const r = await post("/iniciar", {
      sequencia: (c && c.nome) || "", sequencia_id: (c && c.seqId) || "",
      projeto: (c && c.projNome) || "", projeto_caminho: (c && c.projCaminho) || ""
    });
    if (!r.ok) throw new Error(r.erro || "o servidor nao iniciou");
    aplicarStatus(r);
    zerar();
    fila = [];
    pedSel = null; cancelArmado = 0;
    mensagem = ""; mensagemErro = false;
    empurrar({ tipo: "painel", msg: "painel " + VERSAO + " começou a registrar" });
    comecarCaptura();
  } catch (e) {
    logar("erro", "iniciar: " + msgErro(e));
  } finally {
    ocupado = false;
    pintar();
  }
}

async function pausar() {
  if (ocupado || !servidor || servidor.estado !== "gravando") return;
  ocupado = true;
  try {
    pararCaptura();
    const r = await post("/pausar");
    if (!r.ok) throw new Error(r.erro || "o servidor nao pausou");
    aplicarStatus(r);
    pintar();
    await fotoFinal(5000);
    fecharRegistro();
    await esvaziar();
  } catch (e) {
    logar("erro", "pausar: " + msgErro(e));
  } finally {
    ocupado = false;
    pintar();
  }
}

async function retomar() {
  if (ocupado || !servidor || servidor.estado !== "pausado") return;
  ocupado = true;
  try {
    const r = await post("/retomar");
    if (!r.ok) throw new Error(r.erro || "o servidor nao retomou");
    aplicarStatus(r);
    aposPausa = true;
    retomadaPendente = true;
    ultimaRetomada = Date.now();
    ag = null; velAnt = null;
    comecarCaptura();
  } catch (e) {
    logar("erro", "retomar: " + msgErro(e));
  } finally {
    ocupado = false;
    pintar();
  }
}

async function concluir() {
  if (ocupado || !servidor || (servidor.estado !== "gravando" && servidor.estado !== "pausado")) return;
  ocupado = true;
  concluindo = true;     // o olho ja comeca a voltar no clique (nao espera a foto final)
  try { olhoAtualizar(); } catch (_) {}
  try {
    if (servidor.estado === "gravando") {
      pararCaptura();
      const p = await post("/pausar");          // o audio para no clique; a foto final vem depois
      if (p.ok) aplicarStatus(p);
      await fotoFinal(10000);
      fecharRegistro();
    }
    if (perdidos > 0) { empurrar({ tipo: "painel", msg: milhar(perdidos) + " eventos perdidos (fila cheia)" }); perdidos = 0; }
    await esvaziar();
    mensagem = "juntando áudio e tela...";
    mensagemErro = false;
    servidor.estado = "finalizando";
    pintar();
    const r = await post("/concluir");
    if (!r.ok) throw new Error(r.erro || "o servidor nao concluiu");
    aplicarStatus({ estado: "parado", t_gravacao: 0, t_valendo: 0, eventos: 0, pedacos: [], ultima: r.pasta });
    mensagem = "salvo: sessoes\\" + r.sessao;
    zerar();
    fila = [];
    pedSel = null; cancelArmado = 0;
  } catch (e) {
    logar("erro", "concluir: " + msgErro(e));
  } finally {
    ocupado = false;
    concluindo = false;  // deu erro e continua gravando/pausado: o olho volta pro Sharingan sozinho
    pintar();
  }
}

/* 0.3.0 CANCELAR: joga fora a sessao inteira (gravando ou pausada). Nada de foto final nem resumo: para a captura, o
 * servidor fecha os gravadores e move a pasta pra sessoes\_descartadas (nunca apaga). Os eventos na fila vao junto pro lixo. */
async function cancelar() {
  if (ocupado || !servidor || (servidor.estado !== "gravando" && servidor.estado !== "pausado")) return;
  ocupado = true;
  concluindo = true;     // o olho volta ja no clique, como no Concluir
  cancelArmado = 0;
  try { olhoAtualizar(); } catch (_) {}
  try {
    pararCaptura();
    pintar();
    const r = await post("/cancelar");
    if (!r.ok) throw new Error(r.erro || "o servidor nao cancelou");
    aplicarStatus({ estado: "parado", t_gravacao: 0, t_valendo: 0, eventos: 0, pedacos: [] });
    mensagem = "descartada (nada foi salvo): sessoes\\_descartadas\\" + (r.sessao || "");
    mensagemErro = false;
    zerar();
    fila = [];
    pedSel = null;
  } catch (e) {
    mensagem = "nao cancelou: " + msgErro(e);
    mensagemErro = true;
    logar("erro", "cancelar: " + msgErro(e));
  } finally {
    ocupado = false;
    concluindo = false;
    pintar();
  }
}

/* 1o clique arma (o botao vira "DE NOVO?" por 3 s); o 2o clique dentro dos 3 s cancela. Sem caixa de confirmacao. */
function cliqueCancelar() {
  const e = servidor && servidor.estado;
  if (ocupado || !conectado || (e !== "gravando" && e !== "pausado")) return;
  if (cancelArmado && Date.now() - cancelArmado <= T_CANCELAR_ARMADO) return cancelar();
  cancelArmado = Date.now();
  pintar();
}

/* 0.3.0 pedacos: clique no bloco seleciona (de novo = solta); o botao pequeno apaga ou devolve o selecionado */
function pedacosAgora() {
  const s = servidor;
  if (!conectado || !s || (s.estado !== "gravando" && s.estado !== "pausado") || !Array.isArray(s.pedacos)) return [];
  return s.pedacos;
}
function pedacoSelecionado() {
  if (pedSel === null) return null;
  const l = pedacosAgora();
  for (let i = 0; i < l.length; i++) if (l[i].n === pedSel && !l[i].gravando) return l[i];
  return null;
}
function clicouPedaco(n) {
  if (ocupado) return;
  pedSel = pedSel === n ? null : n;
  cancelArmado = 0;
  pintar();
}
async function acaoPedaco() {
  const p = pedacoSelecionado();
  if (ocupado || !p) return;
  ocupado = true;
  pintar();
  try {
    const r = await post(p.apagado ? "/voltar_pedaco" : "/apagar_pedaco", { n: p.n });
    if (!r.ok) throw new Error(r.erro || "o servidor recusou");
    aplicarStatus(r);
    mensagem = p.apagado ? "pedaço " + p.n + " voltou pra gravação" : "pedaço " + p.n + " apagado (fica fora da junção; VOLTAR desfaz)";
    mensagemErro = false;
  } catch (e) {
    mensagem = (p.apagado ? "nao voltou o pedaço " : "nao apagou o pedaço ") + p.n + ": " + msgErro(e);
    mensagemErro = true;
    logar("erro", "pedaço " + p.n + ": " + msgErro(e));
  } finally {
    ocupado = false;
    pintar();
  }
}

function principal() {
  const e = servidor && servidor.estado;
  if (e === "parado") return iniciar();
  if (e === "gravando") return pausar();
  if (e === "pausado") return retomar();
}

const ACOES = { iniciar: iniciar, pausar: pausar, retomar: retomar, concluir: concluir };

/* ------------------------------------------------------------ olho (KAKASHI)
 * Pedido do Luan 14/10: parado = olho com sangue em volta (olho.png); Iniciar = o sangue se junta e vira o
 * Sharingan (ligar_00..17, ~55 ms cada) e ele fica girando (giro_00..11 em loop, ~90 ms) enquanto GRAVA;
 * Pausar = giro parado no quadro em que estava; Retomar = volta a girar; Concluir = ligar_17..00 ao contrario
 * (~45 ms) e volta pro olho.png. Painel aberto/recarregado com a sessao ja gravando = direto pro giro.
 * UM timer so (olhoTimer, setTimeout encadeado). Cada passo so troca o src do <img> (nada do Premiere,
 * nada de rede): nao pesa nos lacos de captura. Parado/pausado = nenhum timer rodando. */
const OLHO_N_LIGAR = 18;
const OLHO_N_GIRO = 12;
const OLHO_MS_LIGAR = 55;
const OLHO_MS_GIRO = 90;
const OLHO_MS_DESLIGAR = 45;
let olhoModo = "inicio";      // inicio (ainda nao viu o servidor) | olho | ligando | giro | pausa | desligando
let olhoQuadro = 0;
let olhoTimer = null;
let olhoSrc = "";
let concluindo = false;       // clicou Concluir: o olho volta ja no clique

function dois(n) { return n < 10 ? "0" + n : String(n); }
function olhoMostrar(src) {
  if (olhoSrc === src) return;
  olhoSrc = src;
  try { if (elOlho) elOlho.src = src; } catch (_) {}
}
function olhoQuadroAtual() {
  if (olhoModo === "ligando" || olhoModo === "desligando") return "icones/ligar_" + dois(olhoQuadro) + ".png";
  if (olhoModo === "giro" || olhoModo === "pausa") return "icones/giro_" + dois(olhoQuadro) + ".png";
  return "icones/olho.png";
}

/* o que o olho TEM que mostrar agora (o servidor e a verdade, como no resto do painel) */
function olhoAlvo() {
  if (!conectado || !servidor || concluindo) return "olho";
  if (servidor.estado === "gravando") return "giro";
  if (servidor.estado === "pausado") return "pausa";
  return "olho";
}

/* um passo da animacao: decide pelo alvo, troca a imagem e agenda o proximo (ou para) */
function olhoPasso() {
  olhoTimer = null;
  let espera = 0;
  try {
    const alvo = olhoAlvo();
    if (olhoModo === "inicio") {
      /* 1a vez que viu o servidor: vai direto pro estado (recarregou gravando = giro, sem animacao) */
      if (conectado && servidor) { olhoModo = alvo; olhoQuadro = 0; }
      if (olhoModo === "giro") espera = OLHO_MS_GIRO;
    } else if (olhoModo === "olho") {
      if (alvo !== "olho") { olhoModo = "ligando"; olhoQuadro = 0; espera = OLHO_MS_LIGAR; }
    } else if (olhoModo === "ligando") {
      if (alvo === "olho") { olhoModo = "desligando"; espera = OLHO_MS_DESLIGAR; }   // volta de onde esta
      else if (olhoQuadro < OLHO_N_LIGAR - 1) { olhoQuadro++; espera = OLHO_MS_LIGAR; }
      else { olhoModo = alvo; olhoQuadro = 0; if (alvo === "giro") espera = OLHO_MS_GIRO; }
    } else if (olhoModo === "giro") {
      if (alvo === "giro") { olhoQuadro = (olhoQuadro + 1) % OLHO_N_GIRO; espera = OLHO_MS_GIRO; }
      else if (alvo === "pausa") olhoModo = "pausa";                                   // congela no quadro atual
      else { olhoModo = "desligando"; olhoQuadro = OLHO_N_LIGAR - 1; espera = OLHO_MS_DESLIGAR; }
    } else if (olhoModo === "pausa") {
      if (alvo === "giro") { olhoModo = "giro"; olhoQuadro = (olhoQuadro + 1) % OLHO_N_GIRO; espera = OLHO_MS_GIRO; }
      else if (alvo === "olho") { olhoModo = "desligando"; olhoQuadro = OLHO_N_LIGAR - 1; espera = OLHO_MS_DESLIGAR; }
    } else if (olhoModo === "desligando") {
      if (alvo !== "olho") { olhoModo = "ligando"; espera = OLHO_MS_LIGAR; }           // voltou a gravar no meio
      else if (olhoQuadro > 0) { olhoQuadro--; espera = OLHO_MS_DESLIGAR; }
      else olhoModo = "olho";
    }
    olhoMostrar(olhoQuadroAtual());
  } catch (_) { espera = 0; }
  if (espera > 0) olhoTimer = setTimeout(olhoPasso, espera);
}

/* chamado pelo pintar(): com a animacao andando, o proprio passo ve a mudanca (<= 90 ms);
 * parado/pausado (sem timer), anda agora */
function olhoAtualizar() {
  if (olhoTimer === null) olhoPasso();
}

/* ------------------------------------------------------------ tela */
function classe(elm, nomes) { if (elm) elm.className = nomes; }
function texto(elm, t) { if (elm && elm.textContent !== t) elm.textContent = t; }

/* 8 bits (14/10): relógio e rótulos dos botões são imagens da fonte pixel (icones/px, gerar_pixel.py). */
function crono(t) {
  if (!elCrono || elCrono._t === t) return;
  elCrono._t = t;
  if (!elCrono._imgs) {
    elCrono.innerHTML = "";
    elCrono._imgs = [];
    for (let i = 0; i < t.length; i++) {
      const im = document.createElement("img");
      im.className = "dig";
      elCrono.appendChild(im);
      elCrono._imgs.push(im);
    }
  }
  for (let i = 0; i < elCrono._imgs.length; i++) {
    const ch = t.charAt(i), im = elCrono._imgs[i];
    const col = ch === ":";
    const src = "icones/px/" + (col ? "d_col" : "d_" + ch) + ".png";
    if (im._src !== src) { im._src = src; im.src = src; im.width = col ? 15 : 30; im.height = 40; }
  }
}
function rotulo(bt, palavra) { if (bt) bt._rot = palavra; }
function pintarRotulo(bt) {
  if (!bt) return;
  const c = bt.className || "";
  const cor = c.indexOf("desligado") >= 0 ? "cinza" : (c.indexOf("pausar") >= 0 ? "amarelo" : (c.indexOf("concluir") >= 0 ? "vermelho" : "branco"));
  const p = bt._rot || "INICIAR";
  const src = "icones/px/bt_" + p.replace(/\./g, "") + "_" + cor + ".png";
  if (bt._src === src) return;
  bt._src = src;
  bt.innerHTML = '<img class="rot" src="' + src + '" width="' + (p.length * 18) + '" height="24" alt="' + p + '">';
}

/* 0.3.0: letra miuda pixel (escala 2) montada letra por letra - "APAGAR PEDAÇO 12" com numero que muda.
 * Mesma fonte 5x7 do titulo/relogio (gerar_pixel.py: c_<codigo>_<cor>.png; cor = branco|amarelo|vermelho|cinza).
 * So refaz as imagens quando o texto ou a cor mudam (a pintura roda a cada 250 ms). */
const COD_MIUDO = { "Ç": "CC", " ": "SP", "·": "PT", ":": "COL", "?": "INT", ".": "DOT" };
const LARG_MIUDA = { " ": 8, "·": 8, ":": 6 };       // o resto 12 px (5 colunas + 1 de espaco, x2)
function pixelTexto(elm, txt, cor) {
  if (!elm) return;
  const chave = txt + "|" + cor;
  if (elm._px === chave) return;
  elm._px = chave;
  elm.innerHTML = "";
  for (let i = 0; i < txt.length; i++) {
    const ch = txt.charAt(i);
    const im = document.createElement("img");
    im.className = "letra";
    im.width = LARG_MIUDA[ch] || 12;
    im.height = 16;
    im.src = "icones/px/c_" + (COD_MIUDO[ch] || ch) + "_" + cor + ".png";
    elm.appendChild(im);
  }
}

function classePedaco(p) {
  if (p.gravando) return "ped ped-rec";
  if (p.apagado) return p.n === pedSel ? "ped ped-apagado-sel" : "ped ped-apagado";
  return p.n === pedSel ? "ped ped-sel" : "ped";
}

/* TRILHO: refaz os blocos so quando muda a estrutura (pedaco novo, apagou, selecionou); a cada pintura so ajusta o
 * tamanho (flex-grow = decimos de segundo; o que esta gravando cresce pelo relogio do painel entre um status e outro) */
function pintarTrilho() {
  if (!elTrilho) return;
  const lista = pedacosAgora();
  if (pedSel !== null && !pedacoSelecionado()) pedSel = null;
  const sig = lista.map(function (p) { return p.n + (p.gravando ? "g" : "") + (p.apagado ? "x" : "") + (p.n === pedSel ? "s" : ""); }).join(",");
  if (elTrilho._sig !== sig) {
    elTrilho._sig = sig;
    elTrilho.innerHTML = "";
    elTrilho._blocos = [];
    lista.forEach(function (p, i) {
      if (i > 0) {
        const c = document.createElement("div");
        c.className = "corte";
        for (let k = 0; k < 4; k++) { const t = document.createElement("div"); t.className = "traco"; c.appendChild(t); }
        elTrilho.appendChild(c);
      }
      const b = document.createElement("div");
      b.className = classePedaco(p);
      b._n = p.n;
      if (!p.gravando) b.addEventListener("click", function () { clicouPedaco(p.n); });
      elTrilho.appendChild(b);
      elTrilho._blocos.push(b);
    });
    if (lista.length) setTimeout(medirTrilho, 400);
  }
  const extra = servidor && servidor.estado === "gravando" ? Math.max(0, (Date.now() - tRecebido) / 1000) : 0;
  lista.forEach(function (p, i) {
    const b = elTrilho._blocos[i];
    if (!b) return;
    const g = String(Math.max(1, Math.round(((p.dur || 0) + (p.gravando ? extra : 0)) * 10)));
    if (b._g !== g) { b._g = g; try { b.style.flexGrow = g; } catch (_) {} }
  });
}

/* sonda barata (o UXP nao tem DevTools pro Luan): larguras de verdade dos blocos no painel.log, pra provar que o
 * flex-grow posto pelo JS pegou (bloco proporcional a duracao). No maximo 12 linhas por carga do painel. */
function medirTrilho() {
  if (trilhoLogs >= 12 || !elTrilho || !elTrilho._blocos || !elTrilho._blocos.length) return;
  try {
    const l = pedacosAgora();
    const larg = elTrilho._blocos.map(function (b) { return b.offsetWidth; });
    trilhoLogs++;
    logar("info", "trilho: " + l.length + " pedaço(s) " + l.map(function (p) { return p.n + "=" + (Math.round((p.dur || 0) * 10) / 10) + "s" + (p.apagado ? "(apagado)" : "") + (p.gravando ? "(gravando)" : ""); }).join(" ") +
                  " -> larguras " + larg.join("/") + " px (trilho " + elTrilho.offsetWidth + " px)");
  } catch (_) {}
}

/* 15/10 12h45 (print no Premiere dele: o painel encaixado tem ~365 px de altura e o CONCLUIR ficava cortado):
 * APAGAR fica do LADO do trilho ("APAGAR 2" / "VOLTAR 2"; o bloco selecionado em amarelo mostra qual) e o CANCELAR do
 * lado do CONCLUIR. Armado, o CANCELAR diz "DE NOVO?" (cabe no botao estreito; a linha de aviso explica). */
function pintarBotoesPedaco() {
  const p = pedacoSelecionado();
  if (p && !ocupado) {
    if (p.apagado) { classe(btPedaco, "mini lado mini-voltar"); pixelTexto(btPedaco, "VOLTAR " + p.n, "amarelo"); }
    else { classe(btPedaco, "mini lado"); pixelTexto(btPedaco, "APAGAR " + p.n, "vermelho"); }
  } else {
    classe(btPedaco, "mini lado mini-off");
    pixelTexto(btPedaco, p ? (p.apagado ? "VOLTAR " : "APAGAR ") + p.n : "APAGAR", "cinza");
  }
  const e = conectado && servidor ? servidor.estado : null;
  if (ocupado || (e !== "gravando" && e !== "pausado")) {
    cancelArmado = 0;
    classe(btCancelar, "mini canto mini-off");
    pixelTexto(btCancelar, "CANCELAR", "cinza");
  } else {
    if (cancelArmado && Date.now() - cancelArmado > T_CANCELAR_ARMADO) cancelArmado = 0;
    if (cancelArmado) { classe(btCancelar, "mini canto mini-armado"); pixelTexto(btCancelar, "DE NOVO?", "amarelo"); }
    else { classe(btCancelar, "mini canto mini-cancelar"); pixelTexto(btCancelar, "CANCELAR", "branco"); }
  }
}

function pintar() {
  texto(elLogo, "KAKASHI");
  texto(elSubLogo, PORTA === 7815 ? "" : "DEV · porta " + PORTA);
  try { olhoAtualizar(); } catch (_) {}     // o olho nunca derruba a pintura da tela
  try { pintarTrilho(); pintarBotoesPedaco(); } catch (e) { if (!AVISADOS.pintar_trilho) { AVISADOS.pintar_trilho = true; logar("erro", "trilho: " + msgErro(e)); } }
  const s = servidor;
  if (!conectado || !s) {
    rotulo(btPrincipal, "INICIAR");
    classe(btPrincipal, "acao desligado");
    classe(btConcluir, "acao concluir fim desligado");
    rotulo(btConcluir, "CONCLUIR"); pintarRotulo(btPrincipal); pintarRotulo(btConcluir);
    classe(elPonto, "ponto ponto-off");
    texto(elStatus, portaOcupada ? "porta " + PORTA + " ocupada por outro programa" : "servidor desligado: abra o atalho Corretor");
    crono("00:00:00");
    texto(elAviso, mensagemErro ? mensagem : "");
    return;
  }
  const e = s.estado;
  let rot = "INICIAR", cls = "acao";
  if (e === "gravando") { rot = "PAUSAR"; cls = "acao pausar"; }
  else if (e === "pausado") { rot = "RETOMAR"; }
  else if (e === "finalizando") { rot = "JUNTANDO..."; cls = "acao desligado"; }
  if (ocupado) cls = cls.indexOf("desligado") < 0 ? cls + " desligado" : cls;
  rotulo(btPrincipal, rot);
  classe(btPrincipal, cls);
  classe(btConcluir, (e === "gravando" || e === "pausado") && !ocupado ? "acao concluir fim" : "acao concluir fim desligado");
  rotulo(btConcluir, "CONCLUIR"); pintarRotulo(btPrincipal); pintarRotulo(btConcluir);
  classe(elPonto, e === "gravando" ? "ponto ponto-rec" : (e === "pausado" ? "ponto ponto-pausa" : "ponto ponto-on"));
  const partes = [];
  if (e === "gravando") partes.push("gravando");
  else if (e === "pausado") partes.push("pausado");
  else if (e === "finalizando") partes.push("juntando");
  else partes.push("pronto");
  if (e === "gravando" || e === "pausado") {
    /* 0.3.0: logo depois do estado (o nome da sequencia e longo e a linha corta no fim) */
    const apagados = pedacosAgora().filter(function (p) { return p.apagado; }).length;
    if (apagados) partes.push(apagados + (apagados > 1 ? " pedaços apagados" : " pedaço apagado"));
    const nomeSeq = (atual && atual.nome) || s.sequencia;
    if (nomeSeq) partes.push(nomeSeq);
    if (e === "gravando") partes.push(s.mic_ok ? "mic ok" : "SEM MIC");
    partes.push(milhar((s.eventos || 0) + fila.length) + " eventos");
  } else if (e === "parado") {
    partes.push("aperte Iniciar");
  }
  texto(elStatus, partes.join(" · "));
  /* 0.3.0: o relogio mostra o que VALE (sem os pedacos apagados); servidor velho sem o campo = o gravado */
  let t = (s.t_valendo !== undefined && s.t_valendo !== null) ? s.t_valendo : (s.t_gravacao || 0);
  if (e === "gravando") t += (Date.now() - tRecebido) / 1000;
  crono(relogio(t));
  if (cancelArmado) {
    texto(elAviso, "clique de novo pra jogar fora esta gravação (vai pra sessoes\\_descartadas)");
    classe(elAviso, "aviso aviso-erro");
  } else {
    texto(elAviso, mensagem);
    classe(elAviso, mensagemErro ? "aviso aviso-erro" : "aviso");
  }
}

/* ------------------------------------------------------------ lacos fixos */
async function lacoComando() {
  try {
    const r = await chamar("/comando?p=" + encodeURIComponent("corretor " + VERSAO), { method: "GET" });
    const s = await r.json();
    if (!s || s.app !== "corretor") {
      /* outro programa respondeu na porta (aconteceu no teste de 13/10 com o app Projetos) */
      if (conectado) pararCaptura();
      conectado = false;
      portaOcupada = true;
      pintar();
      setTimeout(lacoComando, T_COMANDO);
      return;
    }
    portaOcupada = false;
    conectado = true;
    if (!ocupado) {
      aplicarStatus(s);
      /* o servidor e a verdade: painel recarregado no meio de uma sessao volta a registrar sozinho */
      if (s.estado === "gravando" && !capturando) comecarCaptura();
      if (s.estado !== "gravando" && capturando) pararCaptura();
      /* fila sem dono: o servidor esta mesmo parado (sem sessao nem pra reabrir) */
      if (s.estado === "parado" && !capturando && fila.length && !enviando) {
        logar("aviso", milhar(fila.length) + " eventos guardados sem sessao no servidor foram descartados");
        fila = [];
      }
    }
    if (s.acao && ACOES[s.acao]) {
      logar("info", "comando remoto: " + s.acao);
      await ACOES[s.acao]();
    }
  } catch (e) {
    if (conectado) { conectado = false; pararCaptura(); }
  }
  pintar();
  setTimeout(lacoComando, T_COMANDO);
}

async function lacoEnvio() {
  if (conectado && fila.length) { try { await enviar(); } catch (_) {} }
  /* defeito F: a fila cheia descartava calada; agora vira evento quando ha espaco */
  if (perdidos > 0 && fila.length < MAX_FILA * 0.9 && capturando) {
    empurrar({ tipo: "painel", msg: milhar(perdidos) + " eventos perdidos (fila cheia)" });
    perdidos = 0;
  }
  setTimeout(lacoEnvio, T_ENVIO);
}

function lacoCrono() {
  try { pintar(); } catch (_) {}
  setTimeout(lacoCrono, 250);
}

function aoClicar(elm, fn) {
  if (!elm) return;
  const vai = function () {
    if (elm.className.indexOf("desligado") >= 0) return;
    Promise.resolve().then(fn).catch(function (e) { logar("erro", msgErro(e)); });
  };
  elm.addEventListener("click", vai);
  elm.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") vai(); });
}

try {
  window.addEventListener("error", function (ev) { logar("erro", "erro JS: " + (ev && ev.message) + " @" + (ev && ev.lineno)); });
  window.addEventListener("unhandledrejection", function (ev) { logar("erro", "promessa: " + msgErro(ev && ev.reason)); });
} catch (_) {}

aoClicar(btPrincipal, principal);
aoClicar(btConcluir, concluir);
aoClicar(btPedaco, acaoPedaco);         // 0.3.0 (o guard de verdade esta dentro: so com pedaco selecionado)
aoClicar(btCancelar, cliqueCancelar);   // 0.3.0 (2 cliques em 3 s)
pintar();
lacoComando();
lacoEnvio();
lacoCrono();

/* so pro teste fora do Premiere (teste/simular_premiere.js); no UXP e inofensivo */
try {
  globalThis.__CORRETOR = {
    diffFotos: diffFotos, diffProjeto: diffProjeto, diffEfeitos: diffEfeitos, diffTransicoes: diffTransicoes,
    diffMarcadores: diffMarcadores, renumerarFaixas: renumerarFaixas, assinaturaFoto: assinaturaFoto,
    compararFotos: compararFotos, consertar: consertar, alinhar: alinhar, PORTA: PORTA, VERSAO: VERSAO,
    tempoMarcado: tempoMarcado, posNaTimeline: posNaTimeline,
    estado: function () { return { capturando: capturando, fila: fila.length, atual: atual && atual.nome, servidor: servidor, ocupado: ocupado,
                                   ouvintes: ouvintes.length, capac: CAPAC, marcas: MARCAS }; },
    desempenho: function () { return resumoDesempenho(); },
    ocupacao: ocupacao,
    olho: function () { return { modo: olhoModo, quadro: olhoQuadro, src: olhoSrc, timer: olhoTimer !== null }; },
    trilho: function () { return { pedSel: pedSel, cancelArmado: cancelArmado, sig: elTrilho && elTrilho._sig,
                                   pedacos: pedacosAgora(), mensagem: mensagem, mensagemErro: mensagemErro }; }
  };
} catch (_) {}
