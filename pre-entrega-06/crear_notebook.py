"""Genera demo.ipynb, la demostración del flujo de delegación."""
import nbformat as nbf

celdas = [
    nbf.v4.new_markdown_cell(
        "# Demostración: orquestador multi-agente\n\n"
        "Este notebook ejecuta el orquestador con una tarea que exige dos dominios de "
        "especialización (búsqueda en la documentación y cálculo) y una síntesis final. "
        "Las salidas quedan guardadas en el notebook, así que se pueden revisar sin ejecutarlo."
    ),
    nbf.v4.new_code_cell(
        "from dotenv import load_dotenv\nload_dotenv()\n\n"
        "from main import TAREA_DEMO, configurar_logs, ejecutar\nconfigurar_logs()"
    ),
    nbf.v4.new_markdown_cell("## 1. El grafo\n\nTopología jerárquica: todos los especialistas reportan al supervisor."),
    nbf.v4.new_code_cell("from graph import construir_grafo\n\nprint(construir_grafo().get_graph().draw_mermaid())"),
    nbf.v4.new_markdown_cell("## 2. La tarea"),
    nbf.v4.new_code_cell("print(TAREA_DEMO)"),
    nbf.v4.new_markdown_cell(
        "## 3. Ejecución\n\nCada decisión del supervisor, con su evaluación según la rúbrica, "
        "y cada aporte de los especialistas, con las herramientas que usaron."
    ),
    nbf.v4.new_code_cell("traza = await ejecutar(TAREA_DEMO)"),
    nbf.v4.new_markdown_cell("## 4. Resumen del flujo de delegación"),
    nbf.v4.new_code_cell(
        "for d in traza['decisiones']:\n"
        "    print(f\"Paso {d['paso']}: supervisor -> {d['siguiente']}\")\n"
        "print()\n"
        "for c in traza['contribuciones']:\n"
        "    print(f\"Paso {c['paso']}: {c['agente']} usó {', '.join(c['herramientas']) or 'ninguna herramienta'}\")"
    ),
    nbf.v4.new_markdown_cell("## 5. Respuesta final"),
    nbf.v4.new_code_cell("from IPython.display import Markdown\n\nMarkdown(traza['respuesta_final'])"),
]

notebook = nbf.v4.new_notebook()
notebook["cells"] = celdas
notebook.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(notebook, "demo.ipynb")
print("demo.ipynb creado")
