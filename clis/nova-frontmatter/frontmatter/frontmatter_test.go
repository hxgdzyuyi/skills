package frontmatter

import (
	"reflect"
	"testing"
	"unicode/utf8"
)

func TestParse(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		wantData map[string]interface{}
		wantBody string
		wantErr  bool
	}{
		{
			name:     "basic frontmatter",
			input:    "---\nplan_state: doing\n---\n# Title\n",
			wantData: map[string]interface{}{"plan_state": "doing"},
			wantBody: "# Title\n",
		},
		{
			name:     "empty frontmatter",
			input:    "---\n---\nSome content\n",
			wantData: map[string]interface{}{},
			wantBody: "Some content\n",
		},
		{
			name:     "no body",
			input:    "---\nkey: value\n---\n",
			wantData: map[string]interface{}{"key": "value"},
			wantBody: "",
		},
		{
			name:     "nested data",
			input:    "---\nmeta:\n  author: test\n  tags:\n    - go\n    - cli\n---\nbody\n",
			wantData: map[string]interface{}{"meta": map[string]interface{}{"author": "test", "tags": []interface{}{"go", "cli"}}},
			wantBody: "body\n",
		},
		{
			name:    "no frontmatter",
			input:   "# Title\nSome content\n",
			wantErr: true,
		},
		{
			name:    "unclosed frontmatter",
			input:   "---\nkey: value\n",
			wantErr: true,
		},
		{
			name:     "frontmatter ending at EOF without trailing newline",
			input:    "---\nkey: value\n---",
			wantData: map[string]interface{}{"key": "value"},
			wantBody: "",
		},
		{
			name:     "numeric values",
			input:    "---\ncount: 42\nprice: 9.99\n---\n",
			wantData: map[string]interface{}{"count": 42, "price": 9.99},
			wantBody: "",
		},
		{
			name:     "boolean values",
			input:    "---\nenabled: true\ndraft: false\n---\n",
			wantData: map[string]interface{}{"enabled": true, "draft": false},
			wantBody: "",
		},
		{
			name:     "chinese values in frontmatter",
			input:    "---\nsubject: 学科分面\nplan_state: doing\n---\n# 标题\n",
			wantData: map[string]interface{}{"subject": "学科分面", "plan_state": "doing"},
			wantBody: "# 标题\n",
		},
		{
			name:     "chinese body",
			input:    "---\nplan_state: doing\n---\n# 学科分面设计\n\n这是一个包含中文的文档。\n",
			wantData: map[string]interface{}{"plan_state": "doing"},
			wantBody: "# 学科分面设计\n\n这是一个包含中文的文档。\n",
		},
		{
			name:     "UTF-8 BOM prefix",
			input:    "\xef\xbb\xbf---\nplan_state: doing\n---\n# Title\n",
			wantData: map[string]interface{}{"plan_state": "doing"},
			wantBody: "# Title\n",
		},
		{
			name:     "UTF-8 BOM with chinese content",
			input:    "\xef\xbb\xbf---\nsubject: 学科分面\n---\n# 学科分面设计\n",
			wantData: map[string]interface{}{"subject": "学科分面"},
			wantBody: "# 学科分面设计\n",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, body, err := Parse(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Errorf("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Errorf("unexpected error: %v", err)
				return
			}
			if !reflect.DeepEqual(data, tt.wantData) {
				t.Errorf("data mismatch:\n  got:  %v\n  want: %v", data, tt.wantData)
			}
			if body != tt.wantBody {
				t.Errorf("body mismatch:\n  got:  %q\n  want: %q", body, tt.wantBody)
			}
		})
	}
}

func TestSerialize(t *testing.T) {
	data := map[string]interface{}{"plan_state": "done"}
	body := "# Title\n"

	result, err := Serialize(data, body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Verify it can be round-tripped
	parsedData, parsedBody, err := Parse(result)
	if err != nil {
		t.Fatalf("failed to parse serialized output: %v", err)
	}
	if !reflect.DeepEqual(parsedData, data) {
		t.Errorf("data mismatch after round-trip:\n  got:  %v\n  want: %v", parsedData, data)
	}
	if parsedBody != body {
		t.Errorf("body mismatch after round-trip:\n  got:  %q\n  want: %q", parsedBody, body)
	}
}

func TestSerializeChineseContent(t *testing.T) {
	data := map[string]interface{}{
		"plan_state": "doing",
		"subject":    "学科分面",
	}
	body := "# 学科分面设计\n\n这是一个包含中文的测试文档。\n"

	result, err := Serialize(data, body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !utf8.ValidString(result) {
		t.Errorf("output is not valid UTF-8")
	}

	// Verify round-trip
	parsedData, parsedBody, err := Parse(result)
	if err != nil {
		t.Fatalf("failed to parse serialized output: %v", err)
	}
	if parsedData["subject"] != "学科分面" {
		t.Errorf("subject mismatch: got %q, want %q", parsedData["subject"], "学科分面")
	}
	if parsedBody != body {
		t.Errorf("body mismatch:\n  got:  %q\n  want: %q", parsedBody, body)
	}
}

func TestRoundTripChinesePreservesUTF8(t *testing.T) {
	input := "---\nplan_state: doing\nsubject: 学科分面\n---\n# 学科分面设计\n\n这是正文。\n"

	data, body, err := Parse(input)
	if err != nil {
		t.Fatalf("Parse error: %v", err)
	}

	data["plan_state"] = "done"

	output, err := Serialize(data, body)
	if err != nil {
		t.Fatalf("Serialize error: %v", err)
	}

	if !utf8.ValidString(output) {
		t.Fatalf("round-trip output is not valid UTF-8")
	}

	// Verify the chinese body is preserved exactly
	_, parsedBody, err := Parse(output)
	if err != nil {
		t.Fatalf("failed to parse round-trip output: %v", err)
	}
	if parsedBody != body {
		t.Errorf("body changed during round-trip:\n  got:  %q\n  want: %q", parsedBody, body)
	}
}

func TestSerializeRejectsInvalidUTF8Body(t *testing.T) {
	data := map[string]interface{}{"key": "value"}
	body := "valid text \xff\xfe invalid bytes\n"

	_, err := Serialize(data, body)
	if err == nil {
		t.Errorf("expected error for invalid UTF-8 body, got nil")
	}
}
