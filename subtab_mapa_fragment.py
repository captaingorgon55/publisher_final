"""
FRAGMENTO: Sub-tab Mapa Colombia dentro de tab_resultados en app.py

Reemplazá el bloque "with subtab_mapa:" por este código.
Asegurate de tener al inicio de app.py:
    from map_generator import render_carrusel_electoral, carrusel_a_zip
"""

# ── Sub-tab 2: Mapa Colombia — CARRUSEL ──────────────────────
with subtab_mapa:
    datos_territoriales = st.session_state.get("datos_territoriales")
    cands_glob          = st.session_state.get("datos_candidatos", candidatos_validos)

    if not datos_territoriales:
        st.markdown("""
        <div class="ee-preview-empty">
            <div class="ee-preview-empty-icon">🗺️</div>
            <div style="font-weight:600;margin-bottom:6px;">Carrusel de mapas electorales</div>
            <div style="font-size:0.9rem;">
                Primero usá el botón <strong>🚀 Scrapear Registraduría + Mapa</strong>
                para obtener los resultados por departamento.
            </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        deptos = datos_territoriales.get("departamentos", [])
        meta   = datos_territoriales.get("meta", {})

        if not deptos:
            st.warning("No hay datos por departamento. Intentá scrapear de nuevo.")
        else:
            # Info del boletín
            boletin_num = meta.get("boletin")
            mesas       = meta.get("mesas_reportadas")
            if boletin_num or mesas:
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if boletin_num:
                        st.metric("Boletín", f"N° {boletin_num}")
                with col_b2:
                    if mesas:
                        st.metric("Escrutado", f"{mesas:.1f}%")

            # Generar carrusel
            boletin_label = f"Boletín {boletin_num}" if boletin_num else boletin_text

            if "carrusel_tarjetas" not in st.session_state or \
               st.session_state.get("carrusel_boletin") != boletin_num:
                with st.spinner("Generando carrusel de mapas..."):
                    try:
                        from map_generator_sv import render_carrusel_electoral, carrusel_a_zip
                        tarjetas = render_carrusel_electoral(
                            candidatos_globales=cands_glob,
                            departamentos=deptos,
                            boletin_text=boletin_label,
                            meta=meta,
                        )
                        st.session_state["carrusel_tarjetas"] = tarjetas
                        st.session_state["carrusel_boletin"]  = boletin_num
                    except Exception as e:
                        st.error(f"Error generando carrusel: {e}")
                        import traceback
                        with st.expander("Detalles"):
                            st.code(traceback.format_exc())
                        st.stop()

            tarjetas = st.session_state.get("carrusel_tarjetas", [])

            if tarjetas:
                # ── Navegación del carrusel ───────────────────
                TITULOS = [
                    "🗺️ Tarjeta 1 — Ganador por depto",
                    "📊 Tarjeta 2 — Resultados nacionales",
                    "🗺️ Tarjeta 3 — Segundo lugar por depto",
                ]

                if "carrusel_idx" not in st.session_state:
                    st.session_state["carrusel_idx"] = 0

                idx = st.session_state["carrusel_idx"]

                # Indicadores de posición
                st.markdown(
                    "".join([
                        f'<span style="display:inline-block;width:12px;height:12px;'
                        f'border-radius:50%;background:{"#E31B23" if i==idx else "#D0D0D0"};'
                        f'margin:0 4px;"></span>'
                        for i in range(len(tarjetas))
                    ]),
                    unsafe_allow_html=True,
                )
                st.caption(TITULOS[idx])

                # Imagen actual
                st.markdown('<div class="ee-preview-card">', unsafe_allow_html=True)
                st.image(tarjetas[idx])
                st.markdown('</div>', unsafe_allow_html=True)

                # Botones anterior / siguiente
                col_prev, col_dl, col_next = st.columns([1, 2, 1])
                with col_prev:
                    if st.button("← Anterior", disabled=(idx == 0),
                                 key="car_prev", use_container_width=True):
                        st.session_state["carrusel_idx"] -= 1
                        st.rerun()
                with col_next:
                    if st.button("Siguiente →", disabled=(idx == len(tarjetas)-1),
                                 key="car_next", use_container_width=True):
                        st.session_state["carrusel_idx"] += 1
                        st.rerun()

                # ── Descarga individual ───────────────────────
                with col_dl:
                    nombres_archivo = [
                        f"01-mapa-ganador-{boletin_label.lower().replace(' ','-')}.png",
                        f"02-resultados-{boletin_label.lower().replace(' ','-')}.png",
                        f"03-mapa-segundo-{boletin_label.lower().replace(' ','-')}.png",
                    ]
                    buf_single = BytesIO()
                    tarjetas[idx].save(buf_single, format="PNG")
                    buf_single.seek(0)
                    st.download_button(
                        label="⬇ Descargar esta",
                        data=buf_single,
                        file_name=nombres_archivo[idx],
                        mime="image/png",
                        type="primary",
                        key=f"dl_single_{idx}",
                        use_container_width=True,
                    )

                st.markdown("---")

                # ── Descarga ZIP todas ────────────────────────
                try:
                    from map_generator_sv import carrusel_a_zip
                    zip_bytes = carrusel_a_zip(tarjetas, boletin_label)
                    st.download_button(
                        label="⬇ Descargar las 3 tarjetas en ZIP",
                        data=zip_bytes,
                        file_name=f"carrusel-electoral-{boletin_label.lower().replace(' ','-')}.zip",
                        mime="application/zip",
                        key="dl_zip_carrusel",
                        use_container_width=True,
                    )
                except Exception:
                    pass

                # ── Regenerar ─────────────────────────────────
                if st.button("🔄 Regenerar carrusel", key="regen_carrusel"):
                    for k in ["carrusel_tarjetas", "carrusel_boletin", "carrusel_idx"]:
                        st.session_state.pop(k, None)
                    st.rerun()
