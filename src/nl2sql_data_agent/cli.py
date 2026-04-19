from typing import Any

from nl2sql_data_agent.app import DEPARTMENTS, NL2SQLApp


def _format_table(columns: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "  (no results)"
    col_widths = [
        max(len(str(col)), max(len(str(row[i])) for row in rows))
        for i, col in enumerate(columns)
    ]
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header = (
        "|" + "|".join(f" {col:<{w}} " for col, w in zip(columns, col_widths)) + "|"
    )
    body = "\n".join(
        "|" + "|".join(f" {str(v):<{w}} " for v, w in zip(row, col_widths)) + "|"
        for row in rows
    )
    return f"{sep}\n{header}\n{sep}\n{body}\n{sep}"


def _pick_department() -> str | None:
    options = DEPARTMENTS + ["Random"]
    print("\nSelect a department:")
    for i, d in enumerate(options, 1):
        print(f"  [{i}] {d}")
    while True:
        try:
            choice = input("\nChoice (1-4): ").strip()
        except EOFError, KeyboardInterrupt:
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            selected = options[int(choice) - 1]
            return None if selected == "Random" else selected
        print("  Invalid choice, try again.")


def main() -> None:
    print("=" * 60)
    print("  NL2SQL Data Agent")
    print("=" * 60)

    department = _pick_department()
    app = NL2SQLApp(department=department)

    print(f"\n[INFO] Department: {app.department}")
    print("       All queries are restricted to this department.")
    print('\nType your question. Enter "exit" or "quit" to stop.\n')

    while True:
        try:
            question = input("Question: ").strip()
        except EOFError, KeyboardInterrupt:
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        result = app.ask(question)

        early_stop = result.get("pipeline_early_stop")
        if early_stop:
            print(f"\n{early_stop}\n")
            continue

        error = result.get("sql_executor_error")
        if error:
            print(f"\n[ERROR] {error}\n")
            continue

        sql = result.get("sql_executor_sql_query", "")
        columns = result.get("sql_executor_columns", [])
        rows = result.get("sql_executor_rows", [])
        row_count = result.get("sql_executor_row_count", 0)
        latency = result.get("pipeline_latency", 0)

        print(f"\nSQL: {sql}\n")
        if row_count == 0:
            print("  No results found.")
        else:
            print(_format_table(columns, rows))
            print(f"  {row_count} row(s)  [{latency:.2f}s]\n")


if __name__ == "__main__":
    main()
