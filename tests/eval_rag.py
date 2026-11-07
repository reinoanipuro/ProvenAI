"""Score a RAG version against questions with known answers.

Run from the project root after building the index: python tests/eval_rag.py

Any version works as long as RegulatoryRetriever.search() returns results with
"filename", "text", "page" and "rerank_score", so two implementations can be
compared on equal terms.
A question passes at rank k when a result in the top k comes from the expected
file and has the expected wording in its text or section label.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from backend.rag import RegulatoryRetriever  # noqa: E402

# (regulation, question, expected filename part, expected text in the passage)
QUESTIONS = [
    ("ADA", "minimum clear width of an accessible walking route", "ADA_2010", "403.5.1"),
    ("ADA", "steepest allowed running slope for a ramp", "ADA_2010", "405.2"),
    ("ADA", "how high must handrails be above the walking surface", "ADA_2010", "505.4"),
    ("ADA", "side wall grab bar length next to a toilet", "ADA_2010", "604.5.1"),
    ("ADA", "clear opening width of a doorway", "ADA_2010", "404.2.3"),
    ("PVAG", "clear width of onboard accessible routes on a passenger vessel", "ATBCB", "V403.5.1"),
    ("PVAG", "running slope of ramps on passenger vessels", "ATBCB", "V405.2"),
    ("PVAG", "proposed vessel guidelines handrail height", "ATBCB", "V503.4"),
    ("SOLAS", "definition of a confirmed flashpoint case", "QH110E", "Confirmed case"),
    ("SOLAS", "MSC.532(107)", "QH110E", "MSC.532(107)"),
    ("SOLAS", "new containership entry on the safety equipment certificate", "QH110E", "Containership"),
    ("SOLAS", "number of immersion suits in the record of equipment", "QH110E", "immersion suits"),
    ("COLREG", "how a vessel must behave in fog when others cannot be seen", "MSN1781", "Rule 19"),
    ("COLREG", "factors for deciding a safe speed", "MSN1781", "safe speed"),
    ("COLREG", "which vessel gives way when two power vessels are crossing", "MSN1781", "crossing situation"),
    ("COLREG", "list of signals that indicate distress and need of assistance", "MSN1781", "distress"),
    ("BWM", "ballast water discharge limit of viable organisms per cubic metre", "MS_6.2021", "Regulation D-2"),
    ("BWM", "required volumetric exchange percentage of ballast water", "MS_6.2021", "95 percent"),
    ("BWM", "guidelines for sediment reception facilities in ports", "MEPC.152", "sediment"),
    ("BWM", "how to take ballast water samples", "MEPC.173", "sampling"),
    ("BWM", "what a ballast water management plan must contain", "MEPC.409", "Ballast Water Management Plan"),
    ("Load Line", "how the ship length is defined for load line purposes", "MSIS41", "rake of keel"),
    ("Load Line", "minimum bow height requirement", "MSIS41", "ow height"),
    ("Load Line", "Montserrat load lines regulations citation", "SRO-No", "Citation"),
    ("MARPOL", "do stationary hotel ships need oil filtering equipment", "TSA MARPOL", "hotel ships"),
    ("MARPOL", "new emission control areas Canadian Arctic and Norwegian Sea", "QF520E", "Canadian Arctic"),
]

# Nothing in the documents answers these, so a good system should score them low.
OUT_OF_SCOPE = [
    "minimum Wi-Fi speed in passenger cabins",
    "price of a cruise ticket to the Caribbean",
    "recommended pizza oven temperature in the galley",
    "DNV hull plate thickness requirement for passenger ships",
    "ventilation rate required for a passenger cabin sauna",
    "minimum crew salary under the maritime labour convention",
]


def _matches(result: dict, expected_file: str, expected_text: str) -> bool:
    in_file = expected_file.lower() in result["filename"].lower()
    searchable = (result.get("section", "") + " " + result["text"]).lower()
    return in_file and expected_text.lower() in searchable


def main() -> None:
    retriever = RegulatoryRetriever()
    ranks: list[int | None] = []
    per_regulation: dict[str, list[int | None]] = {}
    correct_top_scores: list[float] = []
    for regulation, question, expected_file, expected_text in QUESTIONS:
        results = retriever.search(question, top_k=10)
        rank = next(
            (
                position
                for position, result in enumerate(results, start=1)
                if _matches(result, expected_file, expected_text)
            ),
            None,
        )
        ranks.append(rank)
        per_regulation.setdefault(regulation, []).append(rank)
        if rank == 1:
            correct_top_scores.append(results[0]["rerank_score"])
        first = results[0]
        print(
            f"{'miss' if rank is None else f'#{rank}':>5}  {regulation:<10} {question[:58]:<58}"
            f"  top: {first['filename'][:22]} p{first['page']}"
        )

    total = len(ranks)
    for k in (1, 3, 5, 10):
        hits = sum(1 for rank in ranks if rank is not None and rank <= k)
        print(f"Hit@{k:<2} {hits}/{total} = {hits / total:.0%}")
    print(f"MRR    {sum(1 / rank for rank in ranks if rank) / total:.3f}")
    for regulation, items in per_regulation.items():
        hits = sum(1 for rank in items if rank is not None and rank <= 5)
        print(f"  {regulation:<10} top 5: {hits}/{len(items)}")

    if correct_top_scores:
        print(f"Lowest top score on a correct answer: {min(correct_top_scores):.2f}")
    for question in OUT_OF_SCOPE:
        print(f"Out of scope {retriever.search(question, top_k=1)[0]['rerank_score']:>7.2f}  {question}")


if __name__ == "__main__":
    main()
