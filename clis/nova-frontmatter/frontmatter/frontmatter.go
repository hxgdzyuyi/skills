package frontmatter

import (
	"bytes"
	"fmt"
	"strings"
	"unicode/utf8"

	"gopkg.in/yaml.v3"
)

// UTF-8 BOM (Byte Order Mark)
const bom = "\xef\xbb\xbf"

// Parse extracts frontmatter data and body from markdown content.
// Returns parsed YAML data, the remaining body, and any error.
func Parse(content string) (map[string]interface{}, string, error) {
	// Strip UTF-8 BOM if present
	content = strings.TrimPrefix(content, bom)

	if !strings.HasPrefix(content, "---\n") && !strings.HasPrefix(content, "---\r\n") {
		return nil, content, fmt.Errorf("no frontmatter found")
	}

	var rest string
	if strings.HasPrefix(content, "---\r\n") {
		rest = content[5:]
	} else {
		rest = content[4:]
	}

	endIdx := -1
	bodyStart := -1

	// Empty frontmatter: closing --- immediately follows opening ---
	if strings.HasPrefix(rest, "---\n") {
		endIdx = 0
		bodyStart = 4
	} else if strings.HasPrefix(rest, "---\r\n") {
		endIdx = 0
		bodyStart = 5
	} else if idx := strings.Index(rest, "\n---\n"); idx != -1 {
		endIdx = idx
		bodyStart = idx + 5
	} else if idx := strings.Index(rest, "\r\n---\r\n"); idx != -1 {
		endIdx = idx
		bodyStart = idx + 7
	} else if strings.HasSuffix(rest, "\n---") {
		endIdx = len(rest) - 4
		bodyStart = len(rest)
	} else if strings.HasSuffix(rest, "\r\n---") {
		endIdx = len(rest) - 5
		bodyStart = len(rest)
	} else if rest == "---" || rest == "---\n" || rest == "---\r\n" {
		endIdx = 0
		bodyStart = len(rest)
	} else {
		return nil, content, fmt.Errorf("no closing frontmatter delimiter found")
	}

	fmRaw := rest[:endIdx]
	body := rest[bodyStart:]

	data := make(map[string]interface{})
	if strings.TrimSpace(fmRaw) != "" {
		if err := yaml.Unmarshal([]byte(fmRaw), &data); err != nil {
			return nil, body, fmt.Errorf("failed to parse frontmatter: %w", err)
		}
		if data == nil {
			data = make(map[string]interface{})
		}
	}

	return data, body, nil
}

// Serialize reconstructs markdown content from frontmatter data and body.
func Serialize(data map[string]interface{}, body string) (string, error) {
	var buf bytes.Buffer
	encoder := yaml.NewEncoder(&buf)
	encoder.SetIndent(2)
	if err := encoder.Encode(data); err != nil {
		return "", fmt.Errorf("failed to serialize frontmatter: %w", err)
	}
	if err := encoder.Close(); err != nil {
		return "", fmt.Errorf("failed to close YAML encoder: %w", err)
	}

	fmYAML := strings.TrimRight(buf.String(), "\n")

	if !utf8.ValidString(fmYAML) {
		return "", fmt.Errorf("YAML encoder produced invalid UTF-8")
	}

	output := fmt.Sprintf("---\n%s\n---\n%s", fmYAML, body)

	if !utf8.ValidString(output) {
		return "", fmt.Errorf("output contains invalid UTF-8")
	}

	return output, nil
}
