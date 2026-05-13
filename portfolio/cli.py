import typer

app = typer.Typer(help="Portfolio review tool")

@app.callback()
def main():
    pass

if __name__ == "__main__":
    app()
