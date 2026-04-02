package frontmatter

import (
	"reflect"
	"testing"
)

func TestParseValueExplicit(t *testing.T) {
	tests := []struct {
		raw      string
		typeName string
		want     interface{}
		hasErr   bool
	}{
		{"hello", "string", "hello", false},
		{"42", "string", "42", false},
		{"true", "string", "true", false},
		{"42", "number", 42, false},
		{"3.14", "number", 3.14, false},
		{"abc", "number", nil, true},
		{"true", "boolean", true, false},
		{"false", "boolean", false, false},
		{"yes", "boolean", nil, true},
		{"anything", "null", nil, false},
		{`{"key":"val"}`, "json", map[string]interface{}{"key": "val"}, false},
		{`[1,2,3]`, "array", []interface{}{1.0, 2.0, 3.0}, false},
		{`not json`, "json", nil, true},
		{"x", "unknown_type", nil, true},
	}

	for _, tt := range tests {
		result, err := ParseValue(tt.raw, tt.typeName)
		if tt.hasErr {
			if err == nil {
				t.Errorf("ParseValue(%q, %q): expected error", tt.raw, tt.typeName)
			}
			continue
		}
		if err != nil {
			t.Errorf("ParseValue(%q, %q): unexpected error: %v", tt.raw, tt.typeName, err)
			continue
		}
		if !reflect.DeepEqual(result, tt.want) {
			t.Errorf("ParseValue(%q, %q) = %v (%T), want %v (%T)", tt.raw, tt.typeName, result, result, tt.want, tt.want)
		}
	}
}

func TestInferValue(t *testing.T) {
	tests := []struct {
		input string
		want  interface{}
	}{
		{"true", true},
		{"false", false},
		{"null", nil},
		{"42", 42},
		{"3.14", 3.14},
		{"hello", "hello"},
		{"done", "done"},
		{"", ""},
	}

	for _, tt := range tests {
		result := InferValue(tt.input)
		if !reflect.DeepEqual(result, tt.want) {
			t.Errorf("InferValue(%q) = %v (%T), want %v (%T)", tt.input, result, result, tt.want, tt.want)
		}
	}
}
