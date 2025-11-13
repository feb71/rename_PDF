# rename_postnummer_app.py
import streamlit as st
from pathlib import Path
import re
import pandas as pd
import os

st.set_page_config(page_title="Rename PDF til postnummer", layout="wide")

st.title("Bulk rename — PDF → postnummer")
st.markdown(
    """
App for å gi PDF-filer nye navn basert på delen før første `_` i filnavnet,
ekstrahere siffer (fjerne punktum/andre tegn) og håndtere duplikater.
**Viktig:** ta backup av mappen før du kjører endelig rename.
"""
)

with st.expander("Hvordan dette fungerer (kort)"):
    st.write(
        """
        - Henter alle `*.pdf` i valgt mappe.
        - Deler filnavnet ved første `_` og tar den delen.
        - Fjerner alle ikke-siffer (så `44.14.1_20251112.pdf` → `44141.pdf`).
        - Hvis ønsket, forkorter til første N sifre (f.eks. 4 for norsk postnummer).
        - Viser en forhåndsvisning (dry run). Når du er fornøyd: huk av bekreftelse og trykk **Rename**.
        - Ved duplikat legges `_1`, `_2`, ... til.
        """
    )

# --- Brukerinnstillinger ---
col1, col2 = st.columns([2, 1])
with col1:
    folder = st.text_input("Mappe (full sti) med PDF-filer", value=".")
    load_btn = st.button("Last inn filer")
with col2:
    dry_run_default = True
    dry_run = st.checkbox("Tørrkjøring (dry run)", value=dry_run_default)
    first_n = st.number_input("Behold kun første N sifre (0 = alle)", min_value=0, value=0, step=1)
    confirm_backup = st.checkbox("Jeg har tatt backup av mappen (kreves for rename)", value=False)

st.markdown("---")

def compute_new_name(fname: str, keep_ext: str = ".pdf", first_n_digits: int = 0):
    # Ta delen før første underscore
    base = Path(fname).stem
    prefix = base.split("_", 1)[0]
    # Fjern alt som ikke er siffer
    digits = re.sub(r"\D", "", prefix)
    if first_n_digits and digits:
        digits = digits[:first_n_digits]
    if not digits:
        return None  # signal om at vi ikke fant et nytt navn
    return f"{digits}{keep_ext}"

def preview_renames(target_dir: Path, first_n_digits: int = 0):
    rows = []
    for p in sorted(target_dir.glob("*.pdf")):
        old = p.name
        new = compute_new_name(old, first_n_digits=first_n_digits)
        rows.append({"old_name": old, "new_name": new or "(ingen siffer funnet)", "path": str(p)})
    return pd.DataFrame(rows)

# --- Last inn filer og vis forhåndsvisning ---
if load_btn:
    target = Path(folder).expanduser().resolve()
    if not target.exists() or not target.is_dir():
        st.error("Fant ikke mappen — sjekk stien og prøv igjen.")
    else:
        df_preview = preview_renames(target, first_n_digits=first_n)
        # Simulér duplikater i preview (hvilket navn det ville blitt)
        def simulate_unique_names(df):
            taken = set()
            results = []
            for _, r in df.iterrows():
                new = r["new_name"]
                if new is None or new.startswith("("):
                    results.append({"old": r["old_name"], "new": r["new_name"], "final_new": None})
                    continue
                candidate = new
                if candidate in taken:
                    i = 1
                    base = Path(new).stem
                    ext = Path(new).suffix or ".pdf"
                    while True:
                        candidate = f"{base}_{i}{ext}"
                        if candidate not in taken:
                            break
                        i += 1
                taken.add(candidate)
                results.append({"old": r["old_name"], "new": r["new_name"], "final_new": candidate})
            return pd.DataFrame(results)
        df_sim = simulate_unique_names(df_preview)
        st.subheader(f"Forhåndsvisning — filer i {target}")
        st.dataframe(df_sim[["old", "final_new"]].rename(columns={"old":"Gammelt navn","final_new":"Nytt navn (preview)"}), height=400)

        # Vis noen statistikker
        total = len(df_sim)
        skipped = df_sim['final_new'].isna().sum()
        st.info(f"Filer funnet: {total} — Filer som ville blitt hoppet over (ingen siffer): {skipped}")

        # Knapper for å utføre rename
        col_a, col_b = st.columns(2)
        with col_a:
            do_rename = st.button("Rename filer nå", disabled=not confirm_backup)
        with col_b:
            st.write("⚠️ Krever at du har haket av at du har backup før rename aktiveres.")

        # Utfør rename hvis ønsket
        if do_rename:
            if not confirm_backup:
                st.error("Du må bekrefte at du har tatt backup før rename kan kjøres.")
            else:
                renamed = []
                skipped_list = []
                errors = []
                for _, r in df_sim.iterrows():
                    old_name = r["old"]
                    final_new = r["final_new"]
                    p = target / old_name
                    if final_new is None:
                        skipped_list.append(old_name)
                        continue
                    dest = target / final_new
                    # Hvis destination allerede finnes (ekstern), finn nytt unikt navn
                    i = 1
                    base = Path(final_new).stem
                    ext = Path(final_new).suffix or ".pdf"
                    while dest.exists():
                        dest = target / f"{base}_{i}{ext}"
                        i += 1
                    try:
                        os.rename(p, dest)
                        renamed.append((old_name, dest.name))
                    except Exception as e:
                        errors.append((old_name, str(e)))
                st.success(f"Ferdig. Renamet: {len(renamed)} filer. Hoppet over: {len(skipped_list)}. Feil: {len(errors)}.")
                if renamed:
                    st.write("Eksempel (før -> etter):")
                    st.table(pd.DataFrame(renamed, columns=["gammelt","nytt"]).head(20))
                if skipped_list:
                    st.warning("Hoppet over (ingen siffer funnet):")
                    st.write(skipped_list[:50])
                if errors:
                    st.error("Noen feil oppstod ved rename:")
                    st.write(errors[:10])

st.markdown("---")
st.caption("Laget for å automatisere omnavning lokalt. Kjøre lokalt: `streamlit run rename_postnummer_app.py` fra mappen du ønsker eller gi absolutt sti i feltet over.")
