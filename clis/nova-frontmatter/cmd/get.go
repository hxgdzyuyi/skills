package cmd

import (
	"encoding/json"
	"fmt"
	"os"

	"nova-frontmatter/frontmatter"

	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

var getCmd = &cobra.Command{
	Use:   "get [file]",
	Short: "Get a value from frontmatter",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		filePath := args[0]
		path, _ := cmd.Flags().GetString("path")
		outputFmt, _ := cmd.Flags().GetString("output")

		content, err := os.ReadFile(filePath)
		if err != nil {
			return fmt.Errorf("failed to read file: %w", err)
		}

		data, _, err := frontmatter.Parse(string(content))
		if err != nil {
			return err
		}

		tokens, err := frontmatter.ParsePointer(path)
		if err != nil {
			return err
		}

		value, err := frontmatter.PointerGet(data, tokens)
		if err != nil {
			return err
		}

		switch outputFmt {
		case "json":
			b, err := json.MarshalIndent(value, "", "  ")
			if err != nil {
				return fmt.Errorf("failed to marshal JSON: %w", err)
			}
			fmt.Println(string(b))
		case "yaml":
			b, err := yaml.Marshal(value)
			if err != nil {
				return fmt.Errorf("failed to marshal YAML: %w", err)
			}
			fmt.Print(string(b))
		case "text":
			fmt.Println(formatText(value))
		default:
			return fmt.Errorf("unknown output format: %q (supported: text|json|yaml)", outputFmt)
		}
		return nil
	},
}

func formatText(v interface{}) string {
	switch val := v.(type) {
	case nil:
		return "null"
	case string:
		return val
	case bool:
		if val {
			return "true"
		}
		return "false"
	case int:
		return fmt.Sprintf("%d", val)
	case int64:
		return fmt.Sprintf("%d", val)
	case float64:
		return fmt.Sprintf("%g", val)
	default:
		b, err := json.Marshal(val)
		if err != nil {
			return fmt.Sprintf("%v", val)
		}
		return string(b)
	}
}

func init() {
	getCmd.Flags().String("path", "", "JSON Pointer path (RFC 6901)")
	getCmd.Flags().String("output", "json", "Output format (text|json|yaml)")
	getCmd.MarkFlagRequired("path")
	rootCmd.AddCommand(getCmd)
}
