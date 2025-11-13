# rename_postnummer_app.py
import streamlit as st
from pathlib import Path
import pandas as pd
import os
import io
import zipfile
from typing import List, Optional

st.set_page_config(page_title="Rename PDF — lokal eller drag & drop", layout="wide")
st.title("Bulk rename — PDF → del før/etter skilletegn (lokal eller drag&drop)")
st.markdown("""
- Du kan peke på en **lokal mappe** (app kjører lokalt) for å **endre filer på disk** (krever backup).
- Eller **dra & slipp** PDF-filer i feltet under — appen lager da en **ZIP** med de omdøpte filene (originalene påvirkes ikke).
- Standard: **Tørrkjøring = False** (dvs. ved lokal rename vil endringer skje når du bekrefter backup).
""")

with st.expander("Hvordan det fungerer (kort)"):
    st.write("""
    - Velg skilletegn (standard `_`) og om du vil bruke delen **før** eller **etter** skilletegnet.
    - Appen beholder punktum i resultatet som standard.
    - For lokale filer: må bekrefte at du har tatt backup før rename tillates.
    - For opplastede filer: du får nedlastbar ZIP med omdøpte kopier.
    """)

# --- Innstillinger ---
col1, col2 = st.columns([2, 1])
with col1:
    folder = st.text_input("Mappe (full sti) med PDF-filer (la stå tom for kun upload)", value="")
    load_btn = st.button("Last inn lokale filer (henter *.pdf fra denne mappen)")
with col2:
    # default dry_run = False etter ønske
    dry_run = st.checkbox("Tørrkjøring (dry run) — Lokal rename (hvis avkrysset: gjør ikke endringer)", value=False)
    sep = st.text_input("Skilletegn (separator)", value="_", max_chars=3)
    split_side = st.radio("Velg hvilken del som skal brukes:", ("før", "etter"))
    first_n = st.number_input("Behold kun første N tegn (0 = alle)", min_value=0, value=0, step=1)
    keep_dots = st.checkbox("Behold punktum (.) i resultatet", value=True)
    confirm_backup = st.checkbox("Jeg har tatt backup av mappen (kreves for lokal rename)", value=False)

st.markdown("---")

def compute_new_name(fname: str, separator: str, side: str, keep_dots_flag: bool, first_n_chars: int = 0) -> Optional[str]:
    p = Path(fname)
    base = p.stem  # uten .pdf
    if separator and separator in base:
        if side == "før":
            part = base.split(separator, 1)[0]
        else:
            part = base.split(separator, 1)[1]
    else:
        part = base
    part = part.strip()
    if not keep_dots_flag:
        part = part.replace(".", "")
    if first_n_chars and first_n_chars > 0:
        part = part[:first_n_chars]
    if part == "":
        return None
    return f"{part}{p.suffix}"

def simulate_unique_names(proposed: List[str]) -> List[str]:
    """Gjør navn unike ved å legge _1, _2 ... ved behov"""
    taken = set()
    final = []
    for name in proposed:
        if name is None:
            final.append(None)
            continue
        candidate = name
        if candidate in taken:
            i = 1
            base = Path(name).stem
            ext = Path(name).suffix or ".pdf"
            while True:
                candidate = f"{base}_{i}{ext}"
                if candidate not in taken:
                    break
                i += 1
        taken.add(candidate)
        final.append(candidate)
    return final

# --- Håndter lokal mappe preview/rename ---
local_df = None
if load_btn and folder:
    target = Path(folder).expanduser().resolve()
    if not target.exists() or not target.is_dir():
        st.error("Fant ikke mappen — sjekk stien og prøv igjen.")
    else:
        rows = []
        for p in sorted(target.glob("*.pdf")):
            old = p.name
            new = compute_new_name(old, sep, split_side, keep_dots, first_n)
            rows.append({"old_name": old, "proposed": new})
        df = pd.DataFrame(rows)
        df["final_new"] = simulate_unique_names(list(df["proposed"]))
        local_df = df
        st.subheader(f"Lokal forhåndsvisning — filer i {target}")
        st.dataframe(df.rename(columns={"old_name":"Gammelt navn","final_new":"Nytt navn (preview)"}), height=400)
        st.info(f"Filer funnet: {len(df)} — Hoppet over: {df['final_new'].isna().sum()}")

        # Rename-knapp for lokal mappe
        do_local_rename = st.button("Utfør lokal rename (endre filene på disk)", disabled=not confirm_backup)
        if do_local_rename:
            if not confirm_backup:
                st.error("Du må bekrefte at du har tatt backup før rename kan kjøres.")
            else:
                renamed = []
                skipped = []
                errors = []
                for _, r in df.iterrows():
                    old = r["old_name"]
                    final_new = r["final_new"]
                    src = target / old
                    if final_new is None:
                        skipped.append(old)
                        continue
                    dest = target / final_new
                    # finn unikt navn om dest finnes allerede
                    i = 1
                    base = Path(final_new).stem
                    ext = Path(final_new).suffix or ".pdf"
                    while dest.exists():
                        dest = target / f"{base}_{i}{ext}"
                        i += 1
                    try:
                        if dry_run:
                            renamed.append((old, dest.name))
                        else:
                            os.rename(src, dest)
                            renamed.append((old, dest.name))
                    except Exception as e:
                        errors.append((old, str(e)))
                st.success(f"(local rename) Ferdig. (dry_run={dry_run}) Renamet: {len(renamed)}. Hoppet over: {len(skipped)}. Feil: {len(errors)}")
                if renamed:
                    st.table(pd.DataFrame(renamed, columns=["gammelt","nytt"]).head(50))
                if skipped:
                    st.warning("Hoppet over (ingen del funnet):")
                    st.write(skipped[:100])
                if errors:
                    st.error("Feil ved rename:")
                    st.write(errors[:10])

st.markdown("---")

# --- Håndter opplasting (drag & drop) ---
st.subheader("Eller dra & slipp PDF-filer her (opplastede filer pakkes i ZIP med nye navn)")
uploaded = st.file_uploader("Dra flere filer hit eller klikk for å velge", accept_multiple_files=True, type=["pdf"])

if uploaded:
    # Bygg preview
    rows = []
    for u in uploaded:
        old = u.name
        new = compute_new_name(old, sep, split_side, keep_dots, first_n)
        rows.append({"old_name": old, "proposed": new, "fileobj": u})
    df_up = pd.DataFrame(rows)
    df_up["final_new"] = simulate_unique_names(list(df_up["proposed"]))
    st.write("Forhåndsvisning av opplastede filer:")
    st.dataframe(df_up.rename(columns={"old_name":"Gammelt navn","final_new":"Nytt navn (preview)"}), height=300)
    st.info(f"Opplastede filer: {len(df_up)} — Hoppet over (ingen del funnet): {df_up['final_new'].isna().sum()}")

    # Lag ZIP med de omdøpte filene (eller gi mulighet til å laste ned bare preview)
    make_zip = st.button("Lag ZIP med omdøpte filer (last ned)")
    if make_zip:
        # Lag ZIP i minnet
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for _, r in df_up.iterrows():
                old = r["old_name"]
                final_new = r["final_new"]
                fileobj = r["fileobj"]
                if final_new is None:
                    # hopp over filer uten foreslått navn
                    continue
                # Les bytes og skriv til zip under final_new navn
                try:
                    file_bytes = fileobj.read()
                    zf.writestr(final_new, file_bytes)
                except Exception as e:
                    st.error(f"Feil ved behandling av {old}: {e}")
        zip_buffer.seek(0)
        st.download_button(
            label="Last ned ZIP med omdøpte filer",
            data=zip_buffer.getvalue(),
            file_name="renamed_pdfs.zip",
            mime="application/zip"
        )

st.markdown("---")
st.caption("Kjør lokalt: `streamlit run rename_postnummer_app.py`. For lokal rename må app kjøre på maskinen som har filene. Opplastede filer behandles kun i appen og tilbys som ZIP — originalene endres ikke.")
