BINARY_NAME = nova-frontmatter
INSTALL_PATH = /usr/local/bin

.PHONY: build test clean link

build:
	go build -o $(BINARY_NAME) .

test:
	go test ./...

clean:
	rm -f $(BINARY_NAME)

link: build
	cp $(BINARY_NAME) $(INSTALL_PATH)/$(BINARY_NAME)
