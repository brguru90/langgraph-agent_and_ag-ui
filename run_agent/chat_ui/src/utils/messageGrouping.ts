import type { ChatDisplayMessage } from "../types";

// Helper function to group messages by conversation blocks
export function groupMessages(messages: ChatDisplayMessage[]): Array<{
  type: 'regular' | 'tool' | 'interrupt' | 'code';
  messages: ChatDisplayMessage[];
  id: string;
}> {
  const groups: Array<{
    type: 'regular' | 'tool' | 'interrupt' | 'code';
    messages: ChatDisplayMessage[];
    id: string;
  }> = [];
  
  let currentGroup: ChatDisplayMessage[] = [];
  let currentType: 'regular' | 'tool' | 'interrupt' | 'code' = 'regular';
  
  for (const message of messages) {
    if (message.message_type === 'interrupt') {
      // Finish current group if exists
      if (currentGroup.length > 0) {
        groups.push({
          type: currentType,
          messages: [...currentGroup],
          id: `group-${groups.length}`
        });
        currentGroup = [];
      }
      
      // Add interrupt as standalone group
      groups.push({
        type: 'interrupt',
        messages: [message],
        id: `interrupt-${message.id}`
      });
      
      currentType = 'regular';
    } else if (message.message_type === 'code') {
      // Code message
      if (currentType !== 'code' && currentGroup.length > 0) {
        groups.push({
          type: currentType,
          messages: [...currentGroup],
          id: `group-${groups.length}`
        });
        currentGroup = [];
      }
      
      currentGroup.push(message);
      currentType = 'code';
    } else if (message.message_type === 'tool' || (message.message_type === 'assistance' && message.toolCalls && message.toolCalls.length > 0 && (!message.content || message.content.trim() === ''))) {
      // Group as tool if:
      // 1. message_type is 'tool' (old logic), OR
      // 2. message_type is 'assistance' but has tool calls and no meaningful text content
      if (currentType !== 'tool' && currentGroup.length > 0) {
        groups.push({
          type: currentType,
          messages: [...currentGroup],
          id: `group-${groups.length}`
        });
        currentGroup = [];
      }
      
      currentGroup.push(message);
      currentType = 'tool';
    } else {
      // Regular message (user/assistance)
      if (currentType !== 'regular' && currentGroup.length > 0) {
        groups.push({
          type: currentType,
          messages: [...currentGroup],
          id: `group-${groups.length}`
        });
        currentGroup = [];
      }
      
      currentGroup.push(message);
      currentType = 'regular';
    }
  }
  
  // Add final group if exists
  if (currentGroup.length > 0) {
    groups.push({
      type: currentType,
      messages: [...currentGroup],
      id: `group-${groups.length}`
    });
  }
  
  return groups;
}
