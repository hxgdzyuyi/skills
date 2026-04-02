package cmd

import (
	"fmt"
	"os"

	"nova-frontmatter/frontmatter"

	"github.com/spf13/cobra"
)

var removeCmd = &cobra.Command{
	Use:   "remove [file]",
	Short: "Remove a value from frontmatter",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		filePath := args[0]
		path, _ := cmd.Flags().GetString("path")

		content, err := os.ReadFile(filePath)
		if err != nil {
			return fmt.Errorf("failed to read file: %w", err)
		}

		data, body, err := frontmatter.Parse(string(content))
		if err != nil {
			return err
		}

		tokens, err := frontmatter.ParsePointer(path)
		if err != nil {
			return err
		}

		result, err := frontmatter.PointerApply(data, tokens, frontmatter.OpRemove, nil, false)
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
	removeCmd.Flags().String("path", "", "JSON Pointer path (RFC 6901)")
	removeCmd.MarkFlagRequired("path")
	rootCmd.AddCommand(removeCmd)
}
