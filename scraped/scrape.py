"""Scrape heemkringhaaltert.be memorial card data into PERSON_SCHEMA JSON."""

BASE_URL = "https://heemkringhaaltert.be/"

LETTER_PAGES = {
    "A": 9498, "B": 9516, "C": 9560, "D": 9580, "D'h": 9706,
    "E": 9715, "F": 9726, "G": 9741, "H": 9758, "I": 9784,
    "J": 9794, "K": 9802, "L": 9809, "M": 9825, "N": 9843,
    "O": 9857, "P": 9863, "Q": 9934, "R": 9871, "S": 9886,
    "T": 9908, "U": 9919, "V": 5695, "Ve": 9953, "W": 9924,
    "X": 9938, "Y": 9942, "Z": 9948,
}
