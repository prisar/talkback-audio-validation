.PHONY: demo replay test clean

demo:
	./run-demo.sh

replay:
	./run-demo.sh --replay

test:
	cd talkback-validator && uv run --with pytest pytest -q

clean:
	rm -rf talkback-validator/runs
