import {
    ChatInputCommandInteraction,
    CacheType,
    ButtonInteraction,
    Role,
    Channel,
    Message,
    GuildMember,
    PermissionsBitField,
    SlashCommandSubcommandBuilder,
    Guild,
    Emoji,
    Sticker
} from "discord.js";
import { AllCommands, Module } from "./type";
import { ChannelSetting, SettingsCommandBuilder, SettingsGroupBuilder, setChannel } from "../types/settings";

async function handleLoggingSubcommands(interaction: ChatInputCommandInteraction<CacheType>, selfMemberId: string) {
    if (!interaction.guild) return;
    if (!interaction.member) return;
    if (!interaction.options) return;
    const loggingGroup = interaction.options.getSubcommand();
    if (loggingGroup === "channel") {
        setChannel("logging", "loggingChannel", interaction, selfMemberId);
    }
}

async function handleWelcomeSubcommands(interaction: ChatInputCommandInteraction<CacheType>, selfMemberId: string) {
    if (!interaction.guild) return;
    if (!interaction.member) return;
    if (!interaction.options) return;
    const group = interaction.options.getSubcommand();
    if (group === "channel") {
        setChannel("welcome", "welcomeChannel", interaction, selfMemberId);
    }
}
async function handleGoodbyeSubcommands(interaction: ChatInputCommandInteraction<CacheType>, selfMemberId: string) {
    if (!interaction.guild) return;
    if (!interaction.member) return;
    if (!interaction.options) return;
    const group = interaction.options.getSubcommand();
    if (group === "channel") {
        setChannel("goodbye", "goodbyeChannel", interaction, selfMemberId);
    }
}

async function handleLevelingSubcommands(interaction: ChatInputCommandInteraction<CacheType>, selfMemberId: string) {
    if (!interaction.guild) return;
    if (!interaction.member) return;
    if (!interaction.options) return;
    const group = interaction.options.getSubcommand();
    if (group === "channel") {
        setChannel("leveling", "levelingChannel", interaction, selfMemberId);
    }
}

export class SettingsModule implements Module {
    commands: AllCommands = [
        new SettingsCommandBuilder()
            .addSettingsGroup(new SettingsGroupBuilder("logging").addChannelSetting(new ChannelSetting("channel")))
            .addSettingsGroup(new SettingsGroupBuilder("welcome").addChannelSetting(new ChannelSetting("channel")))
            .addSettingsGroup(new SettingsGroupBuilder("goodbye").addChannelSetting(new ChannelSetting("channel")))
            .addSettingsGroup(new SettingsGroupBuilder("leveling").addChannelSetting(new ChannelSetting("channel")))
            .addSettingsGroup(
                new SettingsGroupBuilder("reactionroles").addSubcommand(
                    new SlashCommandSubcommandBuilder()
                        .setName("new")
                        .setDescription("Create a reaction role")
                        .addStringOption((msg) => msg.setName("message").setDescription("The message").setRequired(true))
                        .addStringOption((mode) =>
                            mode
                                .setName("mode")
                                .setDescription("Mode to use this in")
                                .setChoices(
                                    {
                                        name: "Normal - Allow adding and removing",
                                        value: "normal"
                                    },
                                    { name: "Add only", value: "add" },
                                    { name: "Remove only", value: "remove" },
                                    {
                                        name: "Only allow a single role",
                                        value: "single"
                                    }
                                )
                                .setRequired(true)
                        )
                        .addRoleOption((role) => role.setName("role").setDescription("The role").setRequired(true))
                        .addRoleOption((role) => role.setName("role-2").setDescription("The role"))
                        .addRoleOption((role) => role.setName("role-3").setDescription("The role"))
                        .addRoleOption((role) => role.setName("role-4").setDescription("The role"))
                        .addRoleOption((role) => role.setName("role-5").setDescription("The role"))
                        .addRoleOption((role) => role.setName("role-6").setDescription("The role"))
                        .addRoleOption((role) => role.setName("role-7").setDescription("The role"))
                        .addRoleOption((role) => role.setName("role-8").setDescription("The role"))
                        .addRoleOption((role) => role.setName("role-9").setDescription("The role"))
                )
            )
    ];
    selfMemberId: string = "";
    async onSlashCommand(interaction: ChatInputCommandInteraction<CacheType>): Promise<void> {
        if (interaction.commandName !== "settings") return;
        if (!interaction.guild) return;
        if (!interaction.member) return;
        if (!interaction.options) return;
        const member = interaction.member as GuildMember;
        if (
            !member.permissions.has(PermissionsBitField.Flags.ManageGuild) &&
            !member.permissions.has(PermissionsBitField.Flags.Administrator)
        ) {
            await interaction.reply({
                content: "You do not have permissions",
                ephemeral: true
            });
            return;
        }

        const subcommand = interaction.options.getSubcommandGroup();
        if (subcommand === "logging") {
            await handleLoggingSubcommands(interaction, this.selfMemberId);
        }
        if (subcommand === "welcome") {
            await handleWelcomeSubcommands(interaction, this.selfMemberId);
        }
        if (subcommand === "goodbye") {
            await handleGoodbyeSubcommands(interaction, this.selfMemberId);
        }
        if (subcommand === "leveling") {
            await handleLevelingSubcommands(interaction, this.selfMemberId);
        }
    }
    async onButtonClick(interaction: ButtonInteraction<CacheType>): Promise<void> {}
    async onRoleCreate(role: Role): Promise<void> {}
    async onRoleEdit(before: Role, after: Role): Promise<void> {}
    async onRoleDelete(role: Role): Promise<void> {}
    async onChannelCreate(role: Channel): Promise<void> {}
    async onChannelEdit(before: Channel, after: Channel): Promise<void> {}
    async onChannelDelete(role: Channel): Promise<void> {}
    async onMessage(msg: Message<boolean>): Promise<void> {}
    async onMessageDelete(msg: Message<boolean>): Promise<void> {}
    async onMessageEdit(before: Message<boolean>, after: Message<boolean>): Promise<void> {}
    async onMemberJoin(member: GuildMember): Promise<void> {}
    async onMemberEdit(before: GuildMember, after: GuildMember): Promise<void> {}
    async onMemberLeave(member: GuildMember): Promise<void> {}
    async onGuildAdd(guild: Guild): Promise<void> {}
    async onGuildRemove(guild: Guild): Promise<void> {}
    async onGuildEdit(before: Guild, after: Guild): Promise<void> {}
    async onEmojiCreate(emoji: Emoji): Promise<void> {}
    async onEmojiDelete(emoji: Emoji): Promise<void> {}
    async onEmojiEdit(before: Emoji, after: Emoji): Promise<void> {}
    async onStickerCreate(sticker: Sticker): Promise<void> {}
    async onStickerDelete(sticker: Sticker): Promise<void> {}
    async onStickerEdit(before: Sticker, after: Sticker): Promise<void> {}
}
