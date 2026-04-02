package frontmatter

import (
	"reflect"
	"testing"
)

func TestParsePointer(t *testing.T) {
	tests := []struct {
		input  string
		want   []string
		hasErr bool
	}{
		{"", []string{}, false},
		{"/foo", []string{"foo"}, false},
		{"/foo/bar", []string{"foo", "bar"}, false},
		{"/foo/0", []string{"foo", "0"}, false},
		{"/a~1b", []string{"a/b"}, false},
		{"/m~0n", []string{"m~n"}, false},
		{"/a~1b~0c", []string{"a/b~c"}, false},
		{"invalid", nil, true},
	}

	for _, tt := range tests {
		tokens, err := ParsePointer(tt.input)
		if tt.hasErr {
			if err == nil {
				t.Errorf("ParsePointer(%q): expected error", tt.input)
			}
			continue
		}
		if err != nil {
			t.Errorf("ParsePointer(%q): unexpected error: %v", tt.input, err)
			continue
		}
		if !reflect.DeepEqual(tokens, tt.want) {
			t.Errorf("ParsePointer(%q) = %v, want %v", tt.input, tokens, tt.want)
		}
	}
}

func TestPointerGet(t *testing.T) {
	data := map[string]interface{}{
		"name": "test",
		"meta": map[string]interface{}{
			"author": "alice",
			"tags":   []interface{}{"go", "cli"},
		},
		"count": 42,
	}

	tests := []struct {
		path   string
		want   interface{}
		hasErr bool
	}{
		{"/name", "test", false},
		{"/meta/author", "alice", false},
		{"/meta/tags/0", "go", false},
		{"/meta/tags/1", "cli", false},
		{"/count", 42, false},
		{"/missing", nil, true},
		{"/meta/tags/5", nil, true},
	}

	for _, tt := range tests {
		tokens, _ := ParsePointer(tt.path)
		result, err := PointerGet(data, tokens)
		if tt.hasErr {
			if err == nil {
				t.Errorf("PointerGet(%q): expected error", tt.path)
			}
			continue
		}
		if err != nil {
			t.Errorf("PointerGet(%q): unexpected error: %v", tt.path, err)
			continue
		}
		if !reflect.DeepEqual(result, tt.want) {
			t.Errorf("PointerGet(%q) = %v, want %v", tt.path, result, tt.want)
		}
	}
}

func TestPointerApplyReplace(t *testing.T) {
	data := map[string]interface{}{
		"plan_state": "doing",
		"meta": map[string]interface{}{
			"author": "alice",
		},
	}

	tokens, _ := ParsePointer("/plan_state")
	result, err := PointerApply(data, tokens, OpReplace, "done", false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	m := result.(map[string]interface{})
	if m["plan_state"] != "done" {
		t.Errorf("expected plan_state=done, got %v", m["plan_state"])
	}
}

func TestPointerApplyReplaceCreateMissing(t *testing.T) {
	data := map[string]interface{}{}

	tokens, _ := ParsePointer("/a/b/c")
	result, err := PointerApply(data, tokens, OpReplace, "value", true)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	m := result.(map[string]interface{})
	a := m["a"].(map[string]interface{})
	b := a["b"].(map[string]interface{})
	if b["c"] != "value" {
		t.Errorf("expected a.b.c=value, got %v", b["c"])
	}
}

func TestPointerApplyAdd(t *testing.T) {
	data := map[string]interface{}{
		"tags": []interface{}{"go"},
	}

	// Add to array using "-"
	tokens, _ := ParsePointer("/tags/-")
	result, err := PointerApply(data, tokens, OpAdd, "cli", false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	m := result.(map[string]interface{})
	tags := m["tags"].([]interface{})
	if len(tags) != 2 || tags[1] != "cli" {
		t.Errorf("expected tags=[go, cli], got %v", tags)
	}

	// Add new key to object
	tokens, _ = ParsePointer("/newkey")
	result, err = PointerApply(m, tokens, OpAdd, "newval", false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	m = result.(map[string]interface{})
	if m["newkey"] != "newval" {
		t.Errorf("expected newkey=newval, got %v", m["newkey"])
	}
}

func TestPointerApplyRemove(t *testing.T) {
	data := map[string]interface{}{
		"keep":   "yes",
		"remove": "this",
	}

	tokens, _ := ParsePointer("/remove")
	result, err := PointerApply(data, tokens, OpRemove, nil, false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	m := result.(map[string]interface{})
	if _, ok := m["remove"]; ok {
		t.Errorf("expected 'remove' key to be deleted")
	}
	if m["keep"] != "yes" {
		t.Errorf("expected 'keep' to remain, got %v", m["keep"])
	}
}

func TestPointerApplyArrayInsert(t *testing.T) {
	data := map[string]interface{}{
		"items": []interface{}{"a", "c"},
	}

	tokens, _ := ParsePointer("/items/1")
	result, err := PointerApply(data, tokens, OpAdd, "b", false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	m := result.(map[string]interface{})
	items := m["items"].([]interface{})
	if !reflect.DeepEqual(items, []interface{}{"a", "b", "c"}) {
		t.Errorf("expected [a, b, c], got %v", items)
	}
}

func TestPointerApplyArrayRemove(t *testing.T) {
	data := map[string]interface{}{
		"items": []interface{}{"a", "b", "c"},
	}

	tokens, _ := ParsePointer("/items/1")
	result, err := PointerApply(data, tokens, OpRemove, nil, false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	m := result.(map[string]interface{})
	items := m["items"].([]interface{})
	if !reflect.DeepEqual(items, []interface{}{"a", "c"}) {
		t.Errorf("expected [a, c], got %v", items)
	}
}
