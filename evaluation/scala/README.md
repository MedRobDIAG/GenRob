# scala — Step 0: misura della fedelta' metrica dei disegni

Prima di adottare un controllo basato sulla coerenza di scala del disegno, ne e'
stata misurata la **premessa**: in una vista quotata, il rapporto fra distanza
disegnata e valore dichiarato e' davvero costante?

Quattro versioni successive del test, ciascuna che corregge un difetto della
precedente:

| file | cosa fa | esito |
|---|---|---|
| `misura_premessa.py` | appaiamento «segmento parallelo piu' vicino» | **ritirato**: misura l'euristica, non il disegno |
| `premessa2.py` | senza appaiamento, su tutte le lunghezze della pagina | **satura** |
| `premessa3.py` | idem, con modello nullo (numeri casuali) | i numeri veri sono spiegati *peggio* dei finti |
| `premessa4.py` | ristretto alle viste pulite, con test sulle linee di quota | la premessa regge **solo entro ±2%**; i bordi di tabella passano il test |

Gli esiti sono versionati (`premessa3.json`, `premessa4.json`,
`premessa_yaskawa.json`): le conclusioni sono leggibili senza rieseguire nulla.

## Per rieseguire

Serve la brochure Yaskawa GP (28 pagine vettoriali), **non versionata** perche'
pesa 64 MB. E' pubblica sul sito del costruttore. Mettila in
`scala/documenti/Yas_GP_Serie_Gesamt_E.pdf`, oppure indica il percorso:

```bash
pip install -r ../requirements-analisi.txt
python3 premessa4.py                      # usa scala/documenti/…
python3 premessa4.py /percorso/al.pdf     # oppure percorso esplicito
YASKAWA_PDF=/percorso/al.pdf python3 premessa4.py
```
