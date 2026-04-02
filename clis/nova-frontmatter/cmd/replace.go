package cmd

import (
	"fmt"
	"os"

	"nova-frontmatter/frontmatter"

	"github.com/spf13/cobra"
)

var replaceCmd = &cobra.Command{
	Use:   "replace [file]",
	Short: "Replace a value in frontmatter",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		filePath := args[0]
		path, _ := cmd.Flags().GetString("path")
		rawValue, _ := cmd.Flags().GetString("value")
		typeName, _ := cmd.Flags().GetString("type")
		createMissing, _ := cmd.Flags().GetBool("create-missing")

		value, err := frontmatter.ParseValue(rawValue, typeName)
		if err != nil {
			return err
		}

		content, err := os.ReadFile(filePath)
		if err != nil {
			return fmt.Errorf("failed to read file: %w", err)
		}

		data, body, err := frontmatter.Parse(string(content))
		if err != nil {
			if createMissing {
				data = make(map[string]interface{})
				body = string(content)
			} else {
				return err
			}
		}

		tokens, err := frontmatter.ParsePointer(path)
		if err != nil {
			return err
		}

		result, err := frontmatter.PointerApply(data, tokens, frontmatter.OpReplace, value, createMissing)
		if err != nil {
			return err
		}

		resultMap, ok := result.(map[string]interface{})
		if !ok {
			return fmt.Errorf("unexpected result type")
		}

		output, err := frontmatter.Serialize(resultMap, body)
		if err != nil {
			return err
		}

		perm := os.FileMode(0644)
		if info, statErr := os.Stat(filePath); statErr == nil {
			perm = info.Mode().Perm()
		}
		return os.WriteFile(filePath, []byte(output), perm)
	},
}

func init() {
	replaceCmd.Flags().String("path", "", "JSON Pointer path (RFC 6901)")
	replaceCmd.Flags().String("value", "", "Target value")
	replaceCmd.Flags().String("type", "", "Value type (string|number|boolean|null|json|array)")
	replaceCmd.Flags().Bool("create-missing", false, "Create missing fields including intermediate paths")
	replaceCmd.MarkFlagRequired("path")
	replaceCmd.MarkFlagRequired("value")
	rootCmd.AddCommand(replaceCmd)
}
