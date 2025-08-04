import { useAgentService, getCompleteGroupedMessages, getPartialGroupedMessages, getMessagesByType } from '../hooks/useAgentService';
import type { GroupedChatDisplayMessage } from '../types';

/**
 * Example component demonstrating efficient usage of grouped messages.
 * Shows how to work with complete vs partial messages and filter by type.
 */
export function GroupedMessageExample() {
  const { groupedMessages } = useAgentService();

  // Get only complete (non-streaming) messages for stable UI
  const completeMessages = getCompleteGroupedMessages(groupedMessages);
  
  // Get streaming messages for loading indicators
  const streamingMessages = getPartialGroupedMessages(groupedMessages);
  
  // Get specific message types
  const assistantMessages = getMessagesByType(groupedMessages, 'assistance');
  const userMessages = getMessagesByType(groupedMessages, 'user');
  const toolMessages = getMessagesByType(groupedMessages, 'tool');

  return (
    <div>
      <h3>Message Grouping Demo</h3>
      
      <div style={{ marginBottom: '20px' }}>
        <h4>Complete Messages ({completeMessages.length})</h4>
        {completeMessages.map(group => (
          <GroupDisplay key={group.id} group={group} />
        ))}
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h4>Streaming Messages ({streamingMessages.length})</h4>
        {streamingMessages.map(group => (
          <GroupDisplay key={group.id} group={group} showPartialIndicator />
        ))}
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h4>Message Type Breakdown</h4>
        <ul>
          <li>Assistant Messages: {assistantMessages.length}</li>
          <li>User Messages: {userMessages.length}</li>
          <li>Tool Messages: {toolMessages.length}</li>
        </ul>
      </div>
    </div>
  );
}

interface GroupDisplayProps {
  group: GroupedChatDisplayMessage;
  showPartialIndicator?: boolean;
}

function GroupDisplay({ group, showPartialIndicator }: GroupDisplayProps) {
  const getGroupColor = (type: string) => {
    switch (type) {
      case 'user': return '#007acc';
      case 'assistance': return '#28a745';
      case 'tool': return '#ffc107';
      case 'interrupt': return '#dc3545';
      default: return '#6c757d';
    }
  };

  // Combine all content from messages in the group
  const combinedContent = group.messages
    .map(msg => msg.content)
    .filter(content => content && content.trim())
    .join('');

  return (
    <div 
      style={{
        border: `2px solid ${getGroupColor(group.group_type)}`,
        borderRadius: '8px',
        padding: '12px',
        marginBottom: '10px',
        backgroundColor: '#f8f9fa'
      }}
    >
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '8px'
      }}>
        <span style={{ 
          fontWeight: 'bold', 
          color: getGroupColor(group.group_type),
          textTransform: 'capitalize'
        }}>
          {group.group_type} Group (ID: {group.id})
        </span>
        {showPartialIndicator && group.partial && (
          <span style={{ 
            backgroundColor: '#ffc107', 
            color: '#212529',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '12px'
          }}>
            ⏳ Streaming
          </span>
        )}
        {!group.partial && (
          <span style={{ 
            backgroundColor: '#28a745', 
            color: 'white',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '12px'
          }}>
            ✅ Complete
          </span>
        )}
      </div>
      
      <div style={{ fontSize: '14px', marginBottom: '8px' }}>
        <strong>Messages in group:</strong> {group.messages.length}
      </div>
      
      {combinedContent && (
        <div style={{ 
          backgroundColor: 'white',
          padding: '8px',
          borderRadius: '4px',
          fontSize: '13px',
          maxHeight: '100px',
          overflow: 'auto'
        }}>
          {combinedContent}
        </div>
      )}
      
      {/* Show tool calls if any */}
      {group.messages.some(msg => msg.toolCalls?.length) && (
        <div style={{ marginTop: '8px', fontSize: '12px' }}>
          <strong>Tool calls:</strong> {
            group.messages
              .flatMap(msg => msg.toolCalls || [])
              .map(tc => tc.name)
              .join(', ')
          }
        </div>
      )}
    </div>
  );
}
