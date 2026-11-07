.PHONY: clean build deploy
clean:
	rm -rf dist
build:
	uv run script.py build
deploy:
	uv run script.py deploy