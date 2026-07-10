/**
 * Forge VS Code Extension — v1.2 stub
 *
 * Full implementation coming in v1.2.
 * See: https://github.com/your-org/forge/blob/main/docs/ROADMAP.md
 */
import * as vscode from 'vscode';

const FORGE_API_URL = vscode.workspace
  .getConfiguration('forge')
  .get<string>('apiUrl', 'http://localhost:8000');

export function activate(context: vscode.ExtensionContext): void {
  const outputChannel = vscode.window.createOutputChannel('Forge');

  // Command: forge.runGoal
  context.subscriptions.push(
    vscode.commands.registerCommand('forge.runGoal', async () => {
      const goal = await vscode.window.showInputBox({
        prompt: 'Enter your goal for Forge to execute',
        placeHolder: 'e.g. Create a hello world Python script and run it',
      });

      if (!goal) return;

      outputChannel.show();
      outputChannel.appendLine(`[Forge] Running goal: ${goal}`);

      try {
        const response = await fetch(`${FORGE_API_URL}/api/v1/executions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ goal }),
        });

        if (!response.ok) {
          const error = await response.text();
          outputChannel.appendLine(`[Forge] Error: ${error}`);
          vscode.window.showErrorMessage(`Forge error: ${error}`);
          return;
        }

        const execution = await response.json() as { id: string; status: string };
        outputChannel.appendLine(
          `[Forge] Execution started: ${execution.id} (status: ${execution.status})`
        );
        vscode.window.showInformationMessage(
          `Forge execution started: ${execution.id}`
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`[Forge] Connection error: ${msg}`);
        vscode.window.showErrorMessage(
          `Could not connect to Forge API at ${FORGE_API_URL}. Is Forge running?`
        );
      }
    })
  );

  // Command: forge.showStatus
  context.subscriptions.push(
    vscode.commands.registerCommand('forge.showStatus', async () => {
      const executionId = await vscode.window.showInputBox({
        prompt: 'Enter execution ID',
        placeHolder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
      });

      if (!executionId) return;

      outputChannel.show();
      try {
        const response = await fetch(
          `${FORGE_API_URL}/api/v1/executions/${executionId}`
        );
        if (!response.ok) {
          outputChannel.appendLine(`[Forge] Execution not found: ${executionId}`);
          return;
        }
        const execution = await response.json() as Record<string, unknown>;
        outputChannel.appendLine(`[Forge] Status for ${executionId}:`);
        outputChannel.appendLine(JSON.stringify(execution, null, 2));
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`[Forge] Error fetching status: ${msg}`);
      }
    })
  );

  // Command: forge.showLogs
  context.subscriptions.push(
    vscode.commands.registerCommand('forge.showLogs', async () => {
      const executionId = await vscode.window.showInputBox({
        prompt: 'Enter execution ID to view logs',
        placeHolder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
      });

      if (!executionId) return;

      outputChannel.show();
      try {
        const response = await fetch(
          `${FORGE_API_URL}/api/v1/logs/${executionId}?limit=100`
        );
        if (!response.ok) {
          outputChannel.appendLine(`[Forge] No logs found for: ${executionId}`);
          return;
        }
        const logs = await response.json() as Array<{
          timestamp: string;
          level: string;
          message: string;
        }>;
        outputChannel.appendLine(`[Forge] Logs for ${executionId}:`);
        for (const log of logs) {
          outputChannel.appendLine(
            `  [${log.timestamp}] ${log.level.toUpperCase()}: ${log.message}`
          );
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`[Forge] Error fetching logs: ${msg}`);
      }
    })
  );

  outputChannel.appendLine('[Forge] Extension activated. Ready.');
}

export function deactivate(): void {}
