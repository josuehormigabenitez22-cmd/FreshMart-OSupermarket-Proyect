import argparse

import pytest

from freshmart.campaigns.cli import crear_parser, main, parse_campaign
from freshmart.campaigns.config import Campaign

PATHS = ["--input", "in", "--silver-dir", "silver"]


def test_parse_campaign_acepta_valor_del_enum_y_nombre_corto() -> None:
    assert parse_campaign("verano_2024") is Campaign.VERANO
    assert parse_campaign("primavera") is Campaign.PRIMAVERA


def test_parse_campaign_desconocida_da_error() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="otoño"):
        parse_campaign("otoño")


def test_parser_campaign_caso_feliz() -> None:
    args = crear_parser().parse_args(["--campaign", "verano", *PATHS])
    assert args.campaign is Campaign.VERANO
    assert not args.all


def test_parser_all_caso_feliz() -> None:
    args = crear_parser().parse_args(["--all", *PATHS])
    assert args.all
    assert args.campaign is None


@pytest.mark.parametrize(
    "seleccion",
    [[], ["--all", "--campaign", "verano"]],
    ids=["ninguna", "las_dos"],
)
def test_parser_exige_exactamente_campaign_o_all(seleccion: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        crear_parser().parse_args([*seleccion, *PATHS])
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "argumentos",
    [
        ["--only-gold", "--silver-dir", "s"],  # falta --gold-dir
        ["--catalog", "--silver-dir", "s"],  # falta --input
        ["--all", "--silver-dir", "s"],  # falta --input
        ["--only-gold", "--catalog", "--silver-dir", "s", "--gold-dir", "g"],
    ],
    ids=[
        "only_gold_sin_gold_dir",
        "catalog_sin_input",
        "all_sin_input",
        "dos_acciones",
    ],
)
def test_main_rechaza_combinaciones_invalidas(argumentos: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argumentos)
    assert excinfo.value.code == 2


def test_only_gold_no_necesita_input() -> None:
    args = crear_parser().parse_args(
        ["--only-gold", "--silver-dir", "s", "--gold-dir", "g"]
    )
    assert args.only_gold and args.input is None
