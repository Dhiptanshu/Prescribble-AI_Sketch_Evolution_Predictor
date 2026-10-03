import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["**/dist/**", "**/node_modules/**", "apps/web/public/**", "report/**", "notebooks/**", "kaggle/**", ".venv*/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["apps/web/src/**/*.{ts,tsx}", "packages/**/*.ts"],
    languageOptions: { globals: { ...globals.browser, ...globals.es2022 } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "@typescript-eslint/no-non-null-assertion": "off",   // noUncheckedIndexedAccess makes `!` the idiom for known-good indexes
    },
  },
  { files: ["**/*.mjs", "eslint.config.js", "apps/web/vite.config.ts", "apps/web/playwright.config.ts", "apps/web/e2e/**/*.ts"], languageOptions: { globals: globals.node } },
);
