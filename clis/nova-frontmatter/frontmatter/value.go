package frontmatter

import (
	"encoding/json"
	"fmt"
	"strconv"
)

// ParseValue parses a raw string value according to the given type name.
// If typeName is empty, the value type is inferred automatically.
func ParseValue(raw string, typeName string) (interface{}, error) {
	if typeName == "" {
		return InferValue(raw), nil
	}

	switch typeName {
	case "string":
		return raw, nil
	case "number":
		if i, err := strconv.Atoi(raw); err == nil {
			return i, nil
		}
		if f, err := strconv.ParseFloat(raw, 64); err == nil {
			return f, nil
		}
		return nil, fmt.Errorf("invalid number: %q", raw)
	case "boolean":
		switch raw {
		case "true":
			return true, nil
		case "false":
			return false, nil
		default:
			return nil, fmt.Errorf("invalid boolean: %q (expected true or false)", raw)
		}
	case "null":
		return nil, nil
	case "json":
		var v interface{}
		if err := json.Unmarshal([]byte(raw), &v); err != nil {
			return nil, fmt.Errorf("invalid JSON: %w", err)
		}
		return v, nil
	case "array":
		var v []interface{}
		if err := json.Unmarshal([]byte(raw), &v); err != nil {
			return nil, fmt.Errorf("invalid JSON array: %w", err)
		}
		return v, nil
	default:
		return nil, fmt.Errorf("unknown type: %q (supported: string|number|boolean|null|json|array)", typeName)
	}
}

// InferValue automatically infers the type of a raw string value.
// Inference order: boolean -> null -> number -> string
func InferValue(raw string) interface{} {
	if raw == "true" {
		return true
	}
	if raw == "false" {
		return false
	}
	if raw == "null" {
		return nil
	}
	if i, err := strconv.Atoi(raw); err == nil {
		return i
	}
	if f, err := strconv.ParseFloat(raw, 64); err == nil {
		return f
	}
	return raw
}
