import type { StageTone, WorkflowTabId } from "../workflowTypes";

type StageTab = {
  id: WorkflowTabId;
  label: string;
  status: string;
  tone: StageTone;
};

type StageTabsProps = {
  tabs: StageTab[];
  activeTab: WorkflowTabId;
  onSelect: (tab: WorkflowTabId) => void;
};

export function StageTabs({
  tabs,
  activeTab,
  onSelect,
}: StageTabsProps) {
  return (
    <div className="tab-strip stage-tab-strip" role="tablist" aria-label="Workflow stages">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          className={activeTab === tab.id ? "tab-button active stage-tab-button" : "tab-button stage-tab-button"}
          onClick={() => onSelect(tab.id)}
        >
          <span className="stage-tab-label">{tab.label}</span>
          <span className={`stage-status-pill ${tab.tone}`}>{tab.status}</span>
        </button>
      ))}
    </div>
  );
}
