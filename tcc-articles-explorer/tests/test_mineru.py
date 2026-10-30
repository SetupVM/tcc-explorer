"""Contrato do MinerU isolado: nenhum subprocesso, modelo ou API real é usado."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from explorador import mineru
from explorador.mineru import ErroMinerU, LeitorMinerU, associar_formulas, verificar_instalacao


MODELO = "PP-FormulaNet_plus-M (MinerU basic/onnx)"


def _documento(*paginas):
    return {
        "schema": "docvortex.middle",
        "schema_version": "2.0",
        "metadata": {
            "file_suffix": "pdf",
            "producer": {"name": "mineru", "version": "4.0.12"},
        },
        "extensions": {"mineru": {"tier": "basic", "parse_mode": "txt"}},
        "pages": list(paginas),
        "is_full_document": False,
    }


def _pagina(numero=1, blocos=None):
    return {
        "page_idx": numero - 1,
        "blocks": blocos if blocos is not None else [_equacao()],
    }


def _equacao(latex="$$x = 1$$", caixa=(0.1, 0.3, 0.6, 0.4), indice=0):
    return {"type": "equation", "index": indice, "bbox": list(caixa), "content": latex}


class ProcessoFalso:
    """Responde ao probe de versões e grava a saída do worker em diretório temporário."""

    def __init__(self):
        self.versoes = {"mineru": "4.0.12", "docvortex": "0.6.1"}
        self.documento = _documento(_pagina())
        self.chamadas = []
        self.workers = []
        self.falha = None
        self.metadata_stdout = None
        self.metadata_returncode = 0

    def __call__(self, argumentos, **opcoes):
        argumentos = [str(arg) for arg in argumentos]
        self.chamadas.append((argumentos, opcoes))
        if "-c" in argumentos:
            return SimpleNamespace(
                returncode=self.metadata_returncode,
                stdout=self.metadata_stdout if self.metadata_stdout is not None else json.dumps(self.versoes),
                stderr="dependência indisponível" if self.metadata_returncode else "",
            )
        self.workers.append((argumentos, opcoes))
        if isinstance(self.falha, Exception):
            raise self.falha
        if self.falha == "exit":
            return SimpleNamespace(returncode=2, stdout="", stderr="modelo local ausente")
        if self.falha != "sem_saida":
            saida = Path(argumentos[argumentos.index("--saida") + 1])
            saida.parent.mkdir(parents=True, exist_ok=True)
            saida.write_text(
                "{json quebrado" if self.falha == "json" else json.dumps(self.documento),
                encoding="utf-8",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    python = tmp_path / "ambiente isolado" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("# executável simulado\n", encoding="utf-8")
    python.chmod(0o700)
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfixture: o worker e simulado\n")
    processo = ProcessoFalso()
    monkeypatch.setattr(mineru.subprocess, "run", processo)
    return SimpleNamespace(
        python=python, pdf=pdf, cache=tmp_path / "cache", processo=processo,
        leitor=LeitorMinerU(python, timeout=30),
    )


def _ler(ambiente, paginas=None, **opcoes):
    return ambiente.leitor.ler(
        ambiente.pdf, ambiente.cache, [1] if paginas is None else paginas, **opcoes,
    )


def _arquivos(pasta):
    return {str(p.relative_to(pasta)): p.read_bytes() for p in pasta.rglob("*") if p.is_file()}


def test_verifica_versoes_sem_importar_ou_executar_modelos(ambiente):
    ok, mensagem = verificar_instalacao(ambiente.python)
    assert ok and "4.0.12" in mensagem
    assert not ambiente.processo.workers
    argumentos, opcoes = ambiente.processo.chamadas[0]
    assert argumentos[0] == str(ambiente.python)
    assert "-I" in argumentos and "-c" in argumentos
    assert opcoes.get("shell", False) is False


@pytest.mark.parametrize("versao", ["3.4.5", "5.0.0", "desconhecida", ""])
def test_instalacao_de_outra_versao_ou_invalida_e_recusada(ambiente, versao):
    ambiente.processo.versoes["mineru"] = versao
    ok, mensagem = verificar_instalacao(ambiente.python)
    assert not ok and mensagem
    assert not ambiente.processo.workers


@pytest.mark.parametrize("resposta", ["", "not-json", "[]", "{}"])
def test_probe_com_saida_invalida_nao_afirma_instalacao_disponivel(ambiente, resposta):
    ambiente.processo.metadata_stdout = resposta
    ok, mensagem = verificar_instalacao(ambiente.python)
    assert not ok and mensagem


def test_probe_com_exit_nao_zero_informa_indisponibilidade(ambiente):
    ambiente.processo.metadata_returncode = 1
    ok, mensagem = verificar_instalacao(ambiente.python)
    assert not ok and mensagem


def test_python_symlink_preserva_caminho_do_venv_no_probe_e_worker(ambiente, tmp_path):
    base = tmp_path / "python-base" / "bin" / "python"
    base.parent.mkdir(parents=True)
    base.write_text("# binário base simulado\n", encoding="utf-8")
    base.chmod(0o700)
    ambiente.python.unlink()
    ambiente.python.symlink_to(base)
    assert verificar_instalacao(ambiente.python)[0]
    leitor = LeitorMinerU(ambiente.python, timeout=30)
    leitor.ler(ambiente.pdf, ambiente.cache, [1])
    assert ambiente.processo.workers
    assert all(
        argumentos[0] == str(ambiente.python.absolute())
        for argumentos, _ in ambiente.processo.chamadas
    )
    assert str(ambiente.python.absolute()) != str(ambiente.python.resolve())


def test_ler_selecao_vazia_nao_executa_nem_probe(ambiente):
    resultado = _ler(ambiente, [])
    assert resultado["formulas"] == []
    assert not ambiente.processo.chamadas


@pytest.mark.parametrize("paginas", [[0], [-1], ["1"], [True]])
def test_rejeita_paginas_invalidas_antes_do_worker(ambiente, paginas):
    with pytest.raises((ErroMinerU, ValueError)):
        _ler(ambiente, paginas)
    assert not ambiente.processo.workers


def test_extrai_equacoes_com_pagina_fisica_e_latex_original(ambiente):
    bruto = r"\[ x _ { i } = 1 \quad (7) \]"
    ambiente.processo.documento = _documento(
        _pagina(1, [_equacao(indice=4)]),
        _pagina(3, [_equacao(bruto, indice=9)]),
    )
    resultado = _ler(ambiente, [1, 3])
    assert resultado["versao"] == "4.0.12"
    assert resultado["modelo"] == MODELO
    assert resultado["reaproveitado"] is False
    assert [(f["id"], f["pagina"]) for f in resultado["formulas"]] == [
        ("mineru-0-4", 1), ("mineru-2-9", 3),
    ]
    formula = resultado["formulas"][1]
    assert formula["latex"] == bruto
    assert "PP-FormulaNet_plus-M" in formula["modelo"]
    assert "4.0.12" in formula["modelo"]
    assert formula["versao"] == "4.0.12"
    assert formula["docvortex"] == "0.6.1"
    assert formula["caixa"] == {"x0": 0.1, "y0": 0.3, "x1": 0.6, "y1": 0.4}


def test_worker_recebe_argumentos_literais_e_modelos_somente_locais(ambiente, tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_MODEL_SOURCE", "huggingface")
    monkeypatch.setenv("MINERU_MODEL_SMALL_BACKEND", "torch")
    pdf = tmp_path / "artigo ; $(touch nao-executar).pdf"
    pdf.write_bytes(ambiente.pdf.read_bytes())
    home = tmp_path / "modelos locais"
    leitor = LeitorMinerU(ambiente.python, timeout=17, model_home=home)
    ambiente.processo.documento = _documento(_pagina(1), _pagina(3))
    leitor.ler(pdf, ambiente.cache, [1, 3])
    argumentos, opcoes = ambiente.processo.workers[0]
    assert argumentos[0] == str(ambiente.python)
    assert "-I" in argumentos
    assert argumentos[argumentos.index("--pdf") + 1] == str(pdf.resolve())
    assert argumentos[argumentos.index("--paginas") + 1] == "1,3"
    assert opcoes.get("shell", False) is False
    assert opcoes["timeout"] == 17
    assert opcoes["env"]["MINERU_MODEL_SMALL_BACKEND"] == "onnx"
    assert opcoes["env"]["MINERU_MODEL_SOURCE"] == "local"
    assert opcoes["env"]["MINERU_HOME"] == str(home.resolve())
    assert not (tmp_path / "nao-executar").exists()


def test_nao_trata_formula_inline_ou_texto_com_delimitador_como_equacao(ambiente):
    ambiente.processo.documento = _documento(_pagina(blocos=[
        {"type": "text", "index": 0, "bbox": [0.1, 0.1, 0.8, 0.2], "content": "Texto $x=1$"},
        {"type": "inline_equation", "index": 1, "bbox": [0.1, 0.2, 0.3, 0.3], "content": "$y=2$"},
        _equacao("$$z=3$$", indice=2),
    ]))
    assert [f["latex"] for f in _ler(ambiente)["formulas"]] == ["$$z=3$$"]


def test_cache_reutiliza_resultado_sem_nova_inferencia(ambiente):
    primeiro = _ler(ambiente)
    segundo = _ler(ambiente)
    assert segundo["reaproveitado"] is True
    assert segundo["formulas"] == primeiro["formulas"]
    assert len(ambiente.processo.workers) == 1


def test_forcar_recalcula_cache_valido(ambiente):
    _ler(ambiente)
    ambiente.processo.documento = _documento(_pagina(blocos=[_equacao("$$y=2$$")]))
    novo = _ler(ambiente, forcar=True)
    assert not novo["reaproveitado"]
    assert novo["formulas"][0]["latex"] == "$$y=2$$"
    assert len(ambiente.processo.workers) == 2
    assert _ler(ambiente)["formulas"] == novo["formulas"]


def test_cache_considera_conteudo_do_pdf_nao_so_caminho(ambiente):
    _ler(ambiente)
    ambiente.pdf.write_bytes(ambiente.pdf.read_bytes() + b"conteudo alterado")
    assert not _ler(ambiente)["reaproveitado"]
    assert len(ambiente.processo.workers) == 2


def test_cache_considera_paginas_solicitadas(ambiente):
    _ler(ambiente)
    ambiente.processo.documento = _documento(_pagina(3))
    resultado = _ler(ambiente, [3])
    assert not resultado["reaproveitado"]
    assert [f["pagina"] for f in resultado["formulas"]] == [3]
    assert len(ambiente.processo.workers) == 2


def test_cache_considera_diretorio_de_modelos(ambiente, tmp_path):
    LeitorMinerU(ambiente.python, timeout=30, model_home=tmp_path / "modelos-a").ler(
        ambiente.pdf, ambiente.cache, [1],
    )
    resultado = LeitorMinerU(ambiente.python, timeout=30, model_home=tmp_path / "modelos-b").ler(
        ambiente.pdf, ambiente.cache, [1],
    )
    assert not resultado["reaproveitado"]
    assert len(ambiente.processo.workers) == 2


@pytest.mark.parametrize("pacote,versao", [("mineru", "4.0.13"), ("docvortex", "0.6.2")])
def test_cache_considera_versoes_dos_dois_pacotes(ambiente, pacote, versao):
    _ler(ambiente)
    ambiente.processo.versoes[pacote] = versao
    if pacote == "mineru":
        ambiente.processo.documento["metadata"]["producer"]["version"] = versao
    assert not _ler(ambiente)["reaproveitado"]
    assert len(ambiente.processo.workers) == 2


@pytest.mark.parametrize("conteudo", ["{json quebrado", "{}", '{"formulas": []}'])
def test_cache_invalido_e_recalculado(ambiente, conteudo):
    _ler(ambiente)
    arquivos = list(ambiente.cache.rglob("*.json"))
    assert arquivos, "O resultado deve persistir em cache JSON."
    for arquivo in arquivos:
        arquivo.write_text(conteudo, encoding="utf-8")
    assert not _ler(ambiente)["reaproveitado"]
    assert len(ambiente.processo.workers) == 2


@pytest.mark.parametrize("falha", ["exit", "json", "sem_saida", "timeout"])
def test_falha_na_releitura_preserva_cache_anterior(ambiente, falha):
    anterior = _ler(ambiente)
    arquivos_antes = _arquivos(ambiente.cache)
    ambiente.processo.falha = (
        subprocess.TimeoutExpired("worker", 30) if falha == "timeout" else falha
    )
    with pytest.raises(ErroMinerU):
        _ler(ambiente, forcar=True)
    assert _arquivos(ambiente.cache) == arquivos_antes
    ambiente.processo.falha = None
    reaproveitado = _ler(ambiente)
    assert reaproveitado["reaproveitado"]
    assert reaproveitado["formulas"] == anterior["formulas"]


@pytest.mark.parametrize("campo,valor", [("schema", "pdf_info"), ("schema_version", "999"), ("pages", {})])
def test_schema_incompativel_nao_sobrescreve_cache(ambiente, campo, valor):
    _ler(ambiente)
    arquivos_antes = _arquivos(ambiente.cache)
    ambiente.processo.documento[campo] = valor
    with pytest.raises(ErroMinerU):
        _ler(ambiente, forcar=True)
    assert _arquivos(ambiente.cache) == arquivos_antes


@pytest.mark.parametrize("paginas", [
    [],  # página pedida ausente
    [_pagina(2)],  # resposta de outra página
    [_pagina(), _pagina()],  # página repetida
    [_pagina(blocos=[_equacao(indice=0), _equacao(indice=0)])],  # ID de fórmula repetido
    [_pagina(blocos=[_equacao(caixa=(0.1, 0.3, 0.1, 0.4))])],  # área nula
    [_pagina(blocos=[_equacao(caixa=(-0.1, 0.3, 0.4, 0.4))])],  # caixa fora da página
])
def test_saida_incompleta_ou_geometria_invalida_preserva_cache(ambiente, paginas):
    _ler(ambiente)
    arquivos_antes = _arquivos(ambiente.cache)
    ambiente.processo.documento = _documento(*paginas)
    with pytest.raises(ErroMinerU):
        _ler(ambiente, forcar=True)
    assert _arquivos(ambiente.cache) == arquivos_antes


def _formula(id_="e1", pagina=1, caixa=(0.1, 0.3, 0.4, 0.4), **extras):
    x0, y0, x1, y1 = caixa
    return {
        "id": id_, "tipo": "formula", "texto": "original Docling", "paginas": [pagina],
        "latex": "principal", "latex_docling": "docling", "latex_dolphin": "dolphin",
        "latex_fonte": "manual", "latex_revisado": True, "numero": "42",
        "caixa": {
            "pagina": pagina, "x0": x0 * 600, "y0": y0 * 800,
            "x1": x1 * 600, "y1": y1 * 800,
            "largura_pagina": 600, "altura_pagina": 800,
        },
        **extras,
    }


def _candidata(id_="mineru-0-0", pagina=1, caixa=(0.1, 0.3, 0.4, 0.4), latex="$$x = 1$$"):
    return {
        "id": id_, "pagina": pagina, "latex": latex, "modelo": MODELO,
        "caixa": dict(zip(("x0", "y0", "x1", "y1"), caixa)),
    }


def test_associacao_duas_colunas_usa_posicao_e_nao_ordem():
    elementos = [_formula("esquerda"), _formula("direita", caixa=(0.6, 0.3, 0.9, 0.4))]
    candidatas = [
        _candidata("dir", caixa=(0.6, 0.3, 0.9, 0.4), latex="$$d=2$$"),
        _candidata("esq", latex="$$e=1$$"),
    ]
    relatorio = associar_formulas(elementos, candidatas, [1])
    assert [e["latex_mineru"] for e in elementos] == ["e=1", "d=2"]
    assert relatorio["associadas"] == 2
    assert relatorio["ambiguas"] == 0
    assert relatorio["sem_correspondencia"] == 0
    assert relatorio["nao_associadas"] == []
    assert isinstance(relatorio["detalhes"], list)


@pytest.mark.parametrize("bruto", [r"$$ x _ { i } = 1 \quad (7) $$", r"\[ x _ { i } = 1 \quad (7) \]"])
def test_associacao_normaliza_alternativa_sem_mudar_escolha_manual(bruto):
    elemento = _formula()
    anterior = deepcopy(elemento)
    candidata = _candidata(latex=bruto)
    candidata_antes = deepcopy(candidata)
    relatorio = associar_formulas([elemento], [candidata], [1])
    assert relatorio["associadas"] == 1
    assert elemento["latex_mineru"] == "x_{i}=1"
    assert elemento["latex_mineru_original"] == bruto
    assert elemento["latex_mineru_modelo"] == MODELO
    assert elemento["latex_mineru_caixa"] == candidata["caixa"]
    assert {k: elemento[k] for k in anterior} == anterior
    assert candidata == candidata_antes


def test_argumento_numerico_final_nao_vira_numero_de_equacao():
    elemento = _formula()
    associar_formulas([elemento], [_candidata(latex="$$L = O(1)$$")], [1])
    assert elemento["latex_mineru"] == "L=O(1)"
    assert elemento.get("latex_mineru_numero") is None
    assert elemento["numero"] == "42"


def test_mesma_posicao_em_paginas_distintas_nao_cruza_associacao():
    elementos = [_formula("pagina1", pagina=1), _formula("pagina3", pagina=3)]
    relatorio = associar_formulas(elementos, [_candidata(pagina=3, latex="$$z=3$$")], [1, 3])
    assert "latex_mineru" not in elementos[0]
    assert elementos[1]["latex_mineru"] == "z=3"
    assert relatorio["associadas"] == 1


def test_selecao_vazia_nao_muta_elementos_nem_candidatas():
    elementos, candidatas = [_formula()], [_candidata()]
    antes = deepcopy((elementos, candidatas))
    relatorio = associar_formulas(elementos, candidatas, [])
    assert (elementos, candidatas) == antes
    assert relatorio["associadas"] == 0


def test_formula_fora_da_selecao_nao_recebe_alternativa():
    elementos = [_formula("p1"), _formula("p2", pagina=2)]
    candidatas = [_candidata("c1"), _candidata("c2", pagina=2)]
    relatorio = associar_formulas(elementos, candidatas, [2])
    assert "latex_mineru" not in elementos[0]
    assert elementos[1]["latex_mineru"] == "x=1"
    assert relatorio["associadas"] == 1


def test_duas_candidatas_viaveis_para_elemento_sao_ambiguas():
    elementos = [_formula()]
    antes = deepcopy(elementos)
    relatorio = associar_formulas(elementos, [_candidata("a"), _candidata("b", latex="$$x=2$$")], [1])
    assert elementos == antes
    assert relatorio["associadas"] == 0
    assert relatorio["ambiguas"] > 0
    assert len(relatorio["nao_associadas"]) == 2


def test_candidata_viavel_para_dois_elementos_nao_e_atribuida_a_nenhum():
    elementos = [_formula("a"), _formula("b")]
    antes = deepcopy(elementos)
    relatorio = associar_formulas(elementos, [_candidata()], [1])
    assert elementos == antes
    assert relatorio["associadas"] == 0
    assert relatorio["ambiguas"] > 0
    assert len(relatorio["nao_associadas"]) == 1


@pytest.mark.parametrize("caixa", [
    (0.1, 0.3, 0.4, 0.4),       # IoU alto
    (0.09, 0.29, 0.41, 0.41),   # inclui a caixa com dimensões próximas
    (0.0, 0.324, 0.7, 0.444),   # IoU baixo; cobre 76% da menor, com razão de áreas 2,8
])
def test_sobreposicao_forte_permite_associacao(caixa):
    elemento = _formula()
    relatorio = associar_formulas([elemento], [_candidata(caixa=caixa)], [1])
    assert relatorio["associadas"] == 1


def test_caixa_muito_maior_nao_associa_so_por_conter_a_formula():
    elemento = _formula()
    anterior = deepcopy(elemento)
    relatorio = associar_formulas([elemento], [_candidata(caixa=(0.0, 0.0, 1.0, 1.0))], [1])
    assert elemento == anterior
    assert relatorio["associadas"] == 0
    assert relatorio["sem_correspondencia"] > 0
    assert len(relatorio["nao_associadas"]) == 1


@pytest.mark.parametrize("caixa", [
    (0.7, 0.7, 0.9, 0.8),  # não se sobrepõe
    (0.35, 0.3, 0.65, 0.4),  # sobreposição insuficiente
    (0.1, 0.3, 0.1, 0.4),  # área nula
    (0.4, 0.3, 0.1, 0.4),  # orientação inválida
    (-0.1, 0.3, 0.4, 0.4),  # fora da página
    (0.1, 0.3, float("nan"), 0.4),
    (0.1, 0.3, float("inf"), 0.4),
])
def test_caixa_invalida_ou_fraca_nao_contamina_formula(caixa):
    elemento = _formula()
    anterior = deepcopy(elemento)
    relatorio = associar_formulas([elemento], [_candidata(caixa=caixa)], [1])
    assert elemento == anterior
    assert relatorio["associadas"] == 0
    assert relatorio["nao_associadas"]


@pytest.mark.parametrize("campo,valor", [
    ("largura_pagina", 0), ("altura_pagina", None), ("x1", "invalido"),
])
def test_caixa_docling_sem_dimensoes_validas_nao_e_associada(campo, valor):
    elemento = _formula()
    elemento["caixa"][campo] = valor
    anterior = deepcopy(elemento)
    relatorio = associar_formulas([elemento], [_candidata()], [1])
    assert elemento == anterior
    assert relatorio["associadas"] == 0


def test_texto_nao_e_tratado_como_formula_por_ter_caixa_compativel():
    elemento = _formula(tipo="texto")
    anterior = deepcopy(elemento)
    relatorio = associar_formulas([elemento], [_candidata()], [1])
    assert elemento == anterior
    assert relatorio["associadas"] == 0


@pytest.fixture
def worker_falso(tmp_path, monkeypatch):
    caminho = Path(__file__).resolve().parents[1] / "scripts" / "mineru_worker.py"
    spec = importlib.util.spec_from_file_location("mineru_worker_em_teste", caminho)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    estado = SimpleNamespace(
        versao="4.0.12", documento=_documento(_pagina(1), _pagina(3)), erro=None, chamadas=[],
    )
    monkeypatch.setattr(worker, "version", lambda nome: estado.versao)
    # O worker normalmente executa em outro processo: sua alteração de ambiente
    # também deve permanecer isolada durante este teste no processo do pytest.
    monkeypatch.setattr(worker.os, "environ", dict(os.environ))
    worker.os.environ.update(
        MINERU_MODEL_SOURCE="huggingface", MINERU_MODEL_SMALL_BACKEND="torch",
        MINERU_MODEL_VLM_SERVER_URL="https://nao-chamar.example/v1",
    )

    def parse(pdf, **opcoes):
        estado.chamadas.append((pdf, opcoes, dict(worker.os.environ)))
        if estado.erro:
            raise estado.erro
        return SimpleNamespace(to_json=lambda: json.dumps(estado.documento))

    pacote = ModuleType("mineru")
    pacote.__path__ = []
    parser = ModuleType("mineru.parser")
    parser.parse = parse
    monkeypatch.setitem(sys.modules, "mineru", pacote)
    monkeypatch.setitem(sys.modules, "mineru.parser", parser)
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(b"%PDF-1.4\nworker com SDK simulado\n")
    saida = tmp_path / "middle.json"
    return SimpleNamespace(worker=worker, estado=estado, pdf=pdf, saida=saida)


def _executar_worker(ambiente, paginas="1,3"):
    return ambiente.worker.main([
        "--pdf", str(ambiente.pdf), "--saida", str(ambiente.saida), "--paginas", paginas,
    ])


def test_worker_chama_sdk_basic_local_com_paginas_fisicas(worker_falso):
    assert _executar_worker(worker_falso, "3,1,3") == 0
    assert json.loads(worker_falso.saida.read_text(encoding="utf-8")) == worker_falso.estado.documento
    pdf, opcoes, ambiente = worker_falso.estado.chamadas[0]
    assert pdf == worker_falso.pdf.resolve()
    assert opcoes == {"tier": "basic", "ocr_mode": "auto", "page_range": "1,3"}
    assert ambiente["MINERU_MODEL_SOURCE"] == "local"
    assert ambiente["MINERU_MODEL_SMALL_BACKEND"] == "onnx"
    assert ambiente["MINERU_TABLE_DEVICE"] == "cpu"
    assert ambiente["MINERU_DEVICE_MODE"] == "cpu"
    assert ambiente["MINERU_MODEL_VLM_SERVER_URL"] == ""
    assert ambiente["HF_HUB_OFFLINE"] == ambiente["TRANSFORMERS_OFFLINE"] == "1"


@pytest.mark.parametrize("paginas", ["", "0", "-1", "1,,3", "1; echo executar", "1.0", "１"])
def test_worker_rejeita_intervalo_invalido_sem_sdk(worker_falso, paginas):
    assert _executar_worker(worker_falso, paginas) != 0
    assert not worker_falso.estado.chamadas
    assert not worker_falso.saida.exists()


@pytest.mark.parametrize("versao", ["3.4.5", "5.0.0"])
def test_worker_rejeita_major_incompativel_antes_de_parse(worker_falso, versao):
    worker_falso.estado.versao = versao
    assert _executar_worker(worker_falso) != 0
    assert not worker_falso.estado.chamadas
    assert not worker_falso.saida.exists()


def test_worker_sdk_com_erro_nao_grava_resultado_parcial(worker_falso, capsys):
    worker_falso.estado.erro = RuntimeError("pesos locais ausentes")
    assert _executar_worker(worker_falso) != 0
    assert "pesos locais ausentes" in capsys.readouterr().err
    assert not worker_falso.saida.exists()


def test_worker_nao_aceita_formato_de_versao_antiga(worker_falso):
    worker_falso.estado.documento = {"pdf_info": []}
    assert _executar_worker(worker_falso) != 0
    assert not worker_falso.saida.exists()
